# TourForge 游览发布校验库

纯 Python 3.11+ 标准库实现，判断条件导航是否会让某类观众卡住。不做界面、
持久化或发布流程。

## 数据模型（`tourforge/model.py`）

```python
from tourforge import Tour, Step, Branch, analyze, replay

tour = Tour(
    entry="S0",                    # 入口步骤名
    attributes=("p0", "p1"),       # 画像属性名（≤48 个），画像开始时完整给定且不变
    steps={                        # ≤50 个步骤
        "S0": Step("S0", branches=(
            Branch("S1", (("p0", True),)),   # 条件：属性=布尔值 的合取；空条件恒真
            Branch("END"),                   # 空条件，排在最后即“否则”
        )),
        "S1": Step("S1", branches=(Branch("END", (("p1", True),)),)),
        "END": Step("END", is_end=True),     # 结束步骤
    },
)
```

- 普通步骤按声明顺序取第一条满足条件的分支（≤3 条），后续匹配分支被遮蔽；
  无匹配分支即卡住；到达结束步骤即成功。
- 画像：`dict[str, bool]`，覆盖全部属性。

## 两个操作

- `analyze(tour) -> Verdict`：所有完整画像都能从入口有限步到达结束步骤时
  `ok=True`；否则 `ok=False` 且 `failure` 给出一个完整反例画像、实际步骤轨迹
  和失败类型（`"stuck"` 无匹配分支 / `"loop"` 循环，循环轨迹含闭合回路的那次
  重访）。
- `replay(tour, profile) -> ReplayResult`：具体执行单个画像，直到结束、卡住或
  首次重访某一步，返回 `trajectory` 与 `outcome`（`"end"|"stuck"|"loop"`）。
  `analyze` 的反例由 `replay` 复现生成，二者轨迹与结论必然一致。

## 实现原理

`analyze` 不枚举画像、不展开路径：画像集合用**有序约简二叉决策图（BDD）**
符号表示（`tourforge/engine.py` 内置一个极小的 ROBDD，属性序固定，节点唯一表
+ apply/neg 缓存）。对每个普通步骤预计算“第 i 条分支被选中”的画像集合
`pre_i = c_i ∧ ¬(c_1 ∨ … ∨ c_{i-1})`（优先遮蔽在此生效），再做最小不动点迭代：

```
W(END) = 全部画像；  W(s) = ⋃ᵢ ( pre_i(s) ∧ W(target_i) )
```

`W(s)` 即从步骤 s 能有限步到达结束步骤的画像集合。`W(entry)` 为全集则通过；
否则从其补集中取一个满足赋值得出完整反例画像，再用 `replay` 生成轨迹与失败
类型。不可达步骤不在 `W(entry)` 的覆盖路径上，不会导致误拒。

## 复杂度

设属性数 A≤48、步骤数 S≤50、每步分支数 B≤3：

- 预计算：O(S·B) 次 BDD 操作。
- 不动点：每轮 O(S·B) 次 BDD 操作；链严格递增，轮数 ≤ 任一步骤到结束步骤的
  最长简单路径 +1（≤ S+1），故 O(S²·B) 次 BDD 操作。
- 单次 BDD 操作代价与节点数相关（带缓存近似 O(n₁·n₂)）；节点数最坏可随 A
  指数增长，但对链式/树状等结构化游览为 O(A) 量级。
- 反例构造：一次 `replay`，O(S) 步。

规模用例（49 步、47 属性，含结构回路）两个版本实测均在毫秒级完成，
远低于 10 秒上限。

## 运行测试

```bash
python3 -m unittest discover -s tests -v
```

测试内容（`tests/test_tourforge.py`）：

- 优先分支遮蔽后续回边（遮蔽时通过、去掉遮蔽后给出循环反例）；
- 仅对部分可达画像漏配分支（stuck 反例）；
- 不可达问题步骤不影响发布；
- 固定随机种子（`random.Random(20261004)`）生成 300 个 ≤6 属性带环小图，
  与“枚举全部画像逐一 replay”的独立穷举参考对照，且每个失败反例都用
  `replay` 核验轨迹与类型完全一致；
- 49 步 / 47 属性规模用例：回边条件为 `p0=假` 时通过（结构回路不可执行），
  改为 `p0=真` 时拒绝并给出可复现的循环反例，两版均满足耗时要求。
