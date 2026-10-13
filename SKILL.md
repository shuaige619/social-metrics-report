---
name: social-metrics-report
description: 当中文电商与自媒体运营需要用本地小红书、抖音内容数据CSV复盘互动率、点击率和点击成本，并检查重复记录、零分母与平台口径差异时使用。
---

# 多平台内容数据复盘

从已有导出的CSV生成中文复盘和可复算表。只读输入，不登录平台，不将曝光、播放当成触达，不把数据相关性写成收入归因或增长保证。

## 支持的输入合同

共同列：row_id、platform、period、post_id、likes、comments、clicks、spend_cny。
- 小红书导出：impressions、saves；互动定义为 likes+comments+saves。
- 抖音导出：views、shares；互动定义为 likes+comments+shares。

这是本技能支持的导出字段合同，不代表平台实时官方指标定义。使用用户给的期间与数据快照时间；不能把period自动当as_of时间。相同row_id跨文件、平台或月份可能不同，保留脚本输出source_id与物理行号，并按(platform, period, row_id)处理记录身份。

开始先读取表头和样例行。其他平台、改名列、不同币种或新的指标定义必须先说明哪些映射未确定并让用户补充；没有确定映射时不能把缺失列当零，不能擅自套用近似字段。可继续报告已确认的输入范围。

## 用计算脚本产出事实

使用本技能的 [scripts/compute_metrics.py](scripts/compute_metrics.py)。将skill-dir替换为此SKILL.md所在目录；文件和输出目录使用真实路径并正确引用含空格路径。为每个输入重复--input：

```sh
python3 "<skill-dir>/scripts/compute_metrics.py" --input "<输入CSV绝对路径>" --input "<第二CSV绝对路径>" --out "<用户输出目录绝对路径>" --period "<YYYY-MM>"
```

用户指定期间时，转换为YYYY-MM并带--period；未指定期间时删除该可选参数，脚本按不同period分别分桶。不能把多个期间的同平台记录混加成一个月报。只向用户指定目录写产物；未指定则使用当前工作目录下outputs/social-metrics-report/。脚本负责解析数字、去重、计数及计算，生成result.json、metrics.csv；为保留历史证据，已有同名产物时脚本拒绝覆盖，复跑应使用新的输出目录。运行失败时读取错误、修正已明确的输入调用；未知映射不能反复猜测。不能绕过失败编出“成功结果”。

成功后真实读取两个文件，用计算结果写report.md。保留脚本的result.json原样，不另写一份推测数字覆盖它。脚本结果包括platforms数组、data_quality及post_rows，分母零/缺失的比率为null；报告呈现为“不可计算”，不是0%。

## 解释规则

- 按每个(platform, period)桶分别展示 denominator_name、denominator、interaction_definition、interactions、engagement_rate、ctr、cpc；不同期间分别解释，无用户授权的跨期合计不作为期间结果。JSON比率是0..1，报告显示百分比时只乘100一次。
- 互动率=互动/该平台分母；CTR=点击/该平台分母；CPC=spend_cny/点击。合计率由分子分母合计计算，不能平均帖级百分比。
- impressions与views，以及saves与shares含义不同。不加总为“全平台总曝光”，不输出混合总互动率或总CTR，不按不同口径率高低排名。
- 同币种的成本/点击可以描述，但不同渠道的点击含义与自然/付费混合仍须保留限制，不能据此宣布获客更便宜。
- 零分母、缺字段、完全重复、同ID不同内容、负数/非法数字，依data_quality逐项说明。全零数据只描述没有记录到量，不能断言“未投放”或“无效帖子”。
- 无上一期间不编造环比，无订单/转化与归因数据不算ROI。下一步建议写为有指标依据的实验假设。

## 交付合同与核验

真实保存三个UTF-8文件：report.md、result.json、metrics.csv。report.md给出期间/快照、分平台口径与数据、数据质量、观察、下一步实验和限制。

result.json由脚本生成：顶层skill="social-metrics-report"、source_ids；platforms每项有platform、period、denominator_name、denominator、interaction_definition、interactions、clicks、spend_cny、engagement_rate、ctr、cpc、source_ids；还有data_quality、post_rows。data_quality保留输入行数、included_input_rows、去重行数、重复映射、冲突与问题；选期间时excluded_rows保留source_id、row_id、period及outside_requested_period原因，不把排除当静默丢行。metrics.csv平台汇总也保留period。combined_financials只涉及同币种花费、点击及CPC，不含总体ER/CTR；报告仍遵守期间边界，不能用跨期财务合计代替指定期间数据。引用每条来源使用脚本给出的source_id，不能仅写笼统“据数据”。

写报告后重新读取产物并解析JSON，核对三文件存在、分平台/期间报告与脚本数值一致、百分比转换正确、零分母没有变成0、没有混合不同口径或期间的总率。指定期间时检查纳入行均符合该period，排除行与原因可追溯。最后报告实际路径和数据缺口，不能声称已刷新账号实时数据。
