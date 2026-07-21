# Paper

这是项目的 LaTeX 初版论文稿。

## 编译

```bash
cd paper
latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex
```

生成的 PDF 会与 `main.tex` 同目录输出。

## 说明

当前稿件定位为“初版论文”，重点描述方法、系统和工程验证。文中的数值示例来自 synthetic data，仅用于验证实现链路，不作为真实市场结论。
