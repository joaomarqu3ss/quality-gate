import argparse
import sys
from pathlib import Path

from quality_gate_lib.config import init_config
from quality_gate_lib.engine import run_quality_gate
from quality_gate_lib.reports import print_console_summary, write_reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Quality Gate Baseline para projetos de código.")
    parser.add_argument("--config", default="quality-gate.yml", help="Caminho para o arquivo YAML de métricas.")
    parser.add_argument("--profile", default=None, help="Nome ou caminho de profile YAML para aplicar antes do config.")
    parser.add_argument("--root", default=None, help="Raiz do projeto a ser escaneado. Sobrescreve project.root.")
    parser.add_argument("--init-config", action="store_true", help="Cria um quality-gate.yml padrão.")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()

    if args.init_config:
        init_config(config_path)
        return 0

    if not config_path.exists():
        print(f"Config não encontrado: {config_path}", file=sys.stderr)
        print("Crie um config com: python quality_gate.py --init-config", file=sys.stderr)
        return 2

    try:
        result = run_quality_gate(config_path, explicit_root=args.root, profile_name=args.profile)
        json_path, html_path = write_reports(result, config_path, explicit_root=args.root, profile_name=args.profile)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    print_console_summary(result, json_path, html_path)
    return 0 if result.passed else 1
