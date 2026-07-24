# Paper

这是项目的最终论文稿，主线为“结构化业绩预告字段之外，公告文本是否提供增量 Alpha”。

## 编译

```bash
python scripts/build_final_paper_assets.py
cd paper
latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex
cp main.pdf "alpha-factor-paper-v$(cat VERSION).pdf"
```

生成的 PDF 会与 `main.tex` 同目录输出。

## 说明

论文表格和图由 `results/workflow/forecast_hold_{20,40,60}.json` 中的确定性结果生成，
对应数据版本与源文件哈希见 `results/paper_update/final/manifest.json`。数值不由 LLM 产生。
论文版本号保存在 `paper/VERSION`，采用 intelligrow 的
`大版本.小版本.MMDD.当日build` 格式。
