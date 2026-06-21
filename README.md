# Quality Gate Baseline

Este pacote cria uma "catraca" de qualidade para a baseline do seu código.

Ele foi pensado para reforçar os pilares de **High Quality Code**:

- **Readability:** alerta e bloqueia arquivos grandes demais.
- **Maintainability:** detecta funções/métodos aparentemente repetidos.
- **Reliability & Security:** valida coverage mínimo como indicador inicial de confiabilidade.
- **Modularity:** incentiva arquivos menores e componentes mais independentes.
- **Efficiency:** limita o escopo escaneado e evita ruído de pastas geradas.
- **Documentation Readability:** alerta sobre documentação longa, sem H1 ou com seções difíceis de revisar em PR.

## Arquivos

```text
quality_gate.py      # CLI principal
quality-gate.yml     # métricas padrão manipuláveis
profiles/            # perfis por stack para CI/CD
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

Use um profile quando quiser aplicar defaults por stack:

```bash
python quality_gate.py --config quality-gate.yml --profile rust --root .
python quality_gate.py --config quality-gate.yml --profile c-cpp --root .
python quality_gate.py --config quality-gate.yml --profile flutter --root .
python quality_gate.py --config quality-gate.yml --profile java-spring --root .
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
quality-gate-report/quality-gate-report.md
```

O Markdown é o formato mais direto para comentários de PR e para o
`GITHUB_STEP_SUMMARY`. O HTML é melhor para inspeção visual completa como
artefato do workflow.

## Profiles por stack

Os profiles ficam em `profiles/` e são aplicados antes do `quality-gate.yml`.
O config versionado já usa `profile: "default"`, e em CI você pode trocar por
`--profile rust`, `--profile node`, `--profile c-cpp` etc. Isso permite manter
um padrão por stack e sobrescrever limites localmente no config do projeto.

Profiles disponíveis:

```text
profiles/default.yml
profiles/java-spring.yml
profiles/angular.yml
profiles/csharp-dotnet.yml
profiles/node.yml
profiles/python.yml
profiles/rust.yml
profiles/flutter.yml
profiles/c-cpp.yml
```

Também é possível apontar para um YAML específico:

```bash
python quality_gate.py --config quality-gate.yml --profile profiles/rust.yml --root .
```

O merge preserva listas sem duplicar itens. Assim, extensões, diretórios
ignorados e caminhos de coverage do profile podem ser combinados com ajustes do
projeto.

## Coverage

O script tenta ler automaticamente:

```text
coverage/lcov.info
coverage/lcov-report/lcov.info
target/site/jacoco/jacoco.xml
coverage.xml
cobertura.xml
coverage/cobertura.xml
coverage/tarpaulin.xml
target/llvm-cov/lcov.info
coverage/coverage.info
```

## Documentação e PRs

Além das métricas de código, o gate avalia documentação Markdown para facilitar
a revisão em pull requests:

```yaml
documentation:
  enabled: true
  max_lines_per_doc: 300
  max_section_lines: 120
  max_heading_depth: 4
  require_h1: true
```

Essas regras geram warnings para documentos longos, seções extensas, ausência de
H1 e hierarquia de headings profunda demais. Por padrão, `quality-gate-report/`
é ignorado para evitar que relatórios gerados entrem no próprio scan.

### Documentação pós-review com LLM

Opcionalmente, o gate pode chamar um LLM depois da revisão completa para gerar
uma documentação pós-review em Markdown. A chave nunca deve ser versionada; use
variável de ambiente ou secret do CI:

```yaml
llm_documentation:
  enabled: true
  provider: "openai-compatible"
  endpoint: "https://api.openai.com/v1/chat/completions"
  api_key_env: "OPENAI_API_KEY"
  model_env: "QUALITY_GATE_LLM_MODEL"
  model: ""
  output_file: "quality-gate-ai-review.md"
  validate_output: true
  fail_if_unavailable: false
  fail_if_invalid: false
```

Quando habilitado, o LLM recebe o resumo do gate, findings, o relatório Markdown
e contexto de arquivos escaneados dentro dos limites configurados. Revise essa
política antes de ativar em repositórios com código sensível ou restrições de
compliance.

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

### Rust

Use o profile Rust e gere coverage em Cobertura/XML ou lcov:

```bash
cargo tarpaulin --out Xml --output-dir coverage
python quality_gate.py --config quality-gate.yml --profile rust --root .
```

Ou com `cargo llvm-cov`:

```bash
cargo llvm-cov --lcov --output-path target/llvm-cov/lcov.info
python quality_gate.py --config quality-gate.yml --profile rust --root .
```

### Flutter / Dart

Use o profile `flutter`. Ele valida arquivos `.dart`, ignora artefatos comuns
de build/codegen e lê o coverage padrão gerado por `flutter test --coverage`:

```bash
flutter test --coverage
python quality_gate.py --config quality-gate.yml --profile flutter --root .
```

### C / C++

Use o profile `c-cpp`. O gate valida arquivos `.c`, `.h`, `.cc`, `.cpp`,
`.cxx`, `.hh`, `.hpp` e `.hxx`, incluindo tamanho por arquivo e assinaturas de
funções repetidas.

```bash
python quality_gate.py --config quality-gate.yml --profile c-cpp --root .
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
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          QUALITY_GATE_LLM_MODEL: ${{ vars.QUALITY_GATE_LLM_MODEL }}
        run: python quality_gate.py --config quality-gate.yml --root .

      - name: Publish Quality Gate Summary
        if: always()
        run: |
          if [ -f quality-gate-report/quality-gate-report.md ]; then
            cat quality-gate-report/quality-gate-report.md >> "$GITHUB_STEP_SUMMARY"
          fi
          if [ -f quality-gate-report/quality-gate-ai-review.md ]; then
            printf '\n\n' >> "$GITHUB_STEP_SUMMARY"
            cat quality-gate-report/quality-gate-ai-review.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload Quality Gate Report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: quality-gate-report
          path: quality-gate-report/
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
