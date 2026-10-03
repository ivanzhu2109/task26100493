# TourForge 游览发布校验库

判断条件导航是否会让某类观众卡住。纯 Python 标准库实现（兼容 3.11+），
只做导航分析，不涉及界面、持久化与发布流程。

## 数据模型

```python
from tourforge import Tour, Step, Branch, analyze, replay, Outcome

tour = Tour(
    attributes=("p0", "p1"),          # 至多 48 个布尔画像属性
    steps={
        # 普通步骤：至多 3 条有序分支，空条件 {} 恒真；
        # 按声明顺序取第一条满足条件的分支，其余被遮蔽。
        "S0": Step("S0", branches=(
            Branch("S1", {"p0": True}),
            Branch("END"),            # 空条件，排在最后相当于 else
        )),
        "S1": Step("S1", branches=(Branch("END", {"p1": True}),)),
        "END": Step("END", is_end=True),   # 结束步骤
    },
    entry="S0",
)
```

- 画像 `profile` 是 `dict[str, bool]`，开始时完整给定，游览期间不变。
- 条件是若干 `属性=布尔值` 的合取（`dict[str, bool]`），空条件恒真。
- 步骤引用与属性名假定合法（输入已在内存中校验过）。

## 两个操作

```python
result = analyze(tour)
if result.passed:
    ...                      # 每种完整画像都能有限步到达结束步骤
else:
    ce = result.counterexample
    ce.profile               # 一个完整反例画像
    ce.trajectory            # 实际步骤轨迹
    ce.failure               # Outcome.STUCK（无匹配分支）或 Outcome.LOOP（循环）

rr = replay(tour, {"p0": True, "p1": False})
rr.trajectory                # 步骤序列；循环时末尾包含闭合回路的那次重访
rr.outcome                   # Outcome.SUCCESS / STUCK / LOOP
```

`analyze` 的反例由 `replay` 实际执行生成，保证可被 `replay(tour, ce.profile)`
原样复现（轨迹与失败类型一致）。

## 实现原理

对固定画像，导航是确定性的。对每个步骤 `s`，用 BDD（`tourforge/bdd.py`，
简约有序二叉决策图）精确表示“从 `s` 出发会失败的画像集合” `fail[s]`：

```
fail[s] = stuck[s]  OR  OR_i ( guard_i[s] AND fail[target_i] )
```

其中 `guard_i` 是“前 i-1 条分支条件都不满足且第 i 条满足”的画像集合
（优先遮蔽由此精确建模），`stuck[s]` 是所有分支条件都不满足的集合。
失败集合是该方程组的**最大不动点**（最小不动点只含卡住，不含循环），
从“全部画像”出发向下迭代到不动点；BDD 是规范表示，收敛判断是指针比较。
`fail[entry]` 为空则通过，否则从中取一个满足画像交给 `replay` 生成反例。
不可达步骤的 `fail` 集合不会传播进入口，因此不会误拒。

## 复杂度

设步骤数 `n ≤ 50`，属性数 `k ≤ 48`，每步分支数 `b ≤ 3`。

- 每次不动点迭代：`O(n · b)` 次 BDD 运算；每次运算代价与 BDD 节点数
  成正比，远小于画像总数 `2^k`。
- 迭代次数：每次迭代至少有一个步骤的失败集合严格缩小，实际收敛
  通常在 `O(n)` 轮内（49 步 / 47 属性的规模用例实测远低于 1 秒）。
- 不枚举画像、不展开路径、不抽样、无超时截断；结论对所有画像精确成立。

## 运行测试

```bash
python3 -m pytest tests/ -q
```

测试包括：≤6 属性小图的独立穷举参考对照（含固定种子随机带环小图）、
优先分支遮蔽回边、仅部分可达画像漏配分支、不可达问题步骤不误拒，
以及 49 步 / 47 属性规模用例的两个版本（各要求 10 秒内完成）。
