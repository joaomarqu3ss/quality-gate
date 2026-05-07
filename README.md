# Quality Gate Baseline

Este pacote cria uma "catraca" de qualidade para a baseline do seu código.

Ele foi pensado para reforçar os pilares de **High Quality Code**:

- **Readability:** alerta e bloqueia arquivos grandes demais.
- **Maintainability:** detecta funções/métodos aparentemente repetidos.
- **Reliability & Security:** valida coverage mínimo como indicador inicial de confiabilidade.
- **Modularity:** incentiva arquivos menores e componentes mais independentes.
- **Efficiency:** limita o escopo escaneado e evita ruído de pastas geradas.

## Arquivos

```text
quality_gate.py      # CLI principal
quality-gate.yml     # métricas padrão manipuláveis
README.md            # este guia
```

## Instalação

O script usa Python 3.10+ e PyYAML.

```bash
pip install pyyaml
```

## Uso básico

Na raiz do projeto:

```bash
python quality_gate.py --config quality-gate.yml --root .
```

O processo retorna:

- `exit code 0` se o gate passou.
- `exit code 1` se o gate falhou.
- `exit code 2` para erro de configuração/uso.

Isso permite usar em CI/CD.

## Gerar config padrão

```bash
python quality_gate.py --init-config
```

## Relatórios gerados

Por padrão, os relatórios saem em:

```text
quality-gate-report/quality-gate-report.json
quality-gate-report/quality-gate-report.html
```

## Coverage

O script tenta ler automaticamente:

```text
coverage/lcov.info
coverage/lcov-report/lcov.info
target/site/jacoco/jacoco.xml
coverage.xml
```

### Angular / TypeScript

Gere coverage:

```bash
ng test --code-coverage
python quality_gate.py --config quality-gate.yml --root .
```

### Java / Spring Boot com Maven e JaCoCo

Exemplo de execução:

```bash
mvn test jacoco:report
python quality_gate.py --config quality-gate.yml --root .
```

Certifique-se de que o caminho `target/site/jacoco/jacoco.xml` esteja em `coverage.paths`.

### Python

Exemplo:

```bash
coverage run -m pytest
coverage xml
python quality_gate.py --config quality-gate.yml --root .
```

## Exemplo para GitHub Actions

```yaml
name: Quality Gate

on:
  pull_request:
  push:
    branches: [ main ]

jobs:
  quality-gate:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install pyyaml

      - name: Run Quality Gate
        run: python quality_gate.py --config quality-gate.yml --root .
```

## Ajustes recomendados

Comece com limites realistas para sua base atual e vá apertando aos poucos:

```yaml
thresholds:
  max_lines_per_file: 400
  warn_lines_per_file: 250
  min_coverage_percent: 80
  max_function_duplicates_allowed: 0
```

Para uma baseline legada, uma boa estratégia é:

1. Rodar o gate.
2. Salvar o relatório.
3. Ajustar os limites para não travar todo o time imediatamente.
4. Reduzir gradualmente os limites em novos PRs.
