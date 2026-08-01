# SHU-OilShock-CN LaTeX 论文模板

本目录是项目的正式论文骨架。版式以 MIT 许可的
`Sustainable-Enjoyment/CUMCM-LaTeX-Template` 为基础，并做了以下合规修正：

- 电子版默认不含承诺书和编号页，第一页直接为摘要；
- 摘要页页码从 `1` 开始并显示在页脚中央；
- 正文页使用中文页眉，左侧显示参赛队号，右侧显示“第 X 页，共 Y 页”；
- A4 纸张，四边页边距均为 25 mm；
- 默认无目录，正文从摘要后的新页开始；
- 增加 Windows / Overleaf 可用的中英文字体回退；
- 按本项目 Q1--Q4 拆分章节，便于多人协作；
- 补齐 BibTeX 参考文献、附录支撑材料列表和编译脚本。

## 文件结构

```text
paper/
├── main.tex                 # 电子提交版入口（默认使用）
├── main-print.tex           # 纸质版入口（含承诺书和编号页）
├── cumcmthesis.cls          # 已适配的模板类
├── references.bib           # 可选的 BibTeX 文献数据库
├── build.ps1                # Windows 一键编译
└── sections/
    ├── abstract.tex
    ├── 1_restatement.tex
    ├── 2_analysis.tex
    ├── 3_assumptions.tex
    ├── 4_symbols.tex
    ├── 5_problem1.tex
    ├── 6_problem2.tex
    ├── 7_problem3.tex
    ├── 8_problem4.tex
    ├── 9_sensitivity.tex
    ├── 10_evaluation.tex
    ├── 11_conclusion.tex
    ├── references.tex       # 默认参考文献列表
    └── A_appendix.tex
```

## 编译

本地安装 MiKTeX 或 TeX Live 后，在 PowerShell 中运行：

```powershell
cd paper
.\build.ps1
```

生成电子提交版 `main.pdf`。若确实需要纸质版，再运行：

```powershell
.\build.ps1 -Mode print
```

生成 `main-print.pdf`。**不得把纸质版 PDF 当作电子论文提交。**

Overleaf 使用方法：上传整个 `paper/` 目录，将编译器设为 XeLaTeX，主文件设为
`main.tex`，连续编译两遍即可。为降低临时环境依赖，模板默认使用
`sections/references.tex`；`references.bib` 保留为可选数据库，若团队以后切换到
BibTeX，再自行启用相应命令。

## 团队协作

- 每名队员只修改自己负责的 `sections/*.tex`，避免同时改 `main.tex`。
- 所有论文数值只能取自 `../results/frozen_numbers.json`、
  `../results/final_numbers.json` 或 `../reports/paper_numbers.csv`。
- 图片优先引用 `../figures/*.pdf`；不要把截图作为论文图。
- 完成正文后再统一写摘要，最后删除所有 `\draftnote{...}`。
- 新增文献必须先核验真实性，再写入 `sections/references.tex` 并在正文引用；如使用
  BibTeX，同时维护 `references.bib`。

## 提交前检查

1. 电子版第一页是摘要，页码为 1，且没有目录。
2. 从正文第一页开始，页眉参赛队号已替换为正式报名号，总页数显示正确。
3. 摘要连同题目和关键词不超过一页。
4. 正文不超过 30 页；附录另计。
5. 全文不存在姓名、学校、赛区等身份信息。
6. 删除所有 `\draftnote`、`TODO`、`待补` 和示例文字。
7. 附录列出全部支撑材料，并提供完整可运行代码。
8. 电子论文为单一 PDF，文件大小不超过 20 MB。

## 上游许可

模板类源自：<https://github.com/Sustainable-Enjoyment/CUMCM-LaTeX-Template>。
MIT 许可证全文见 `LICENSE-Sustainable-CUMCM-Template.txt`，本项目保留原作者版权声明。
