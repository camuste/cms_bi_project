# =============================================================================
# scheduler.py — CMS BI Project
# Câmara Municipal de Salvador — Automação de Coleta
# =============================================================================
# Modos de execução:
#   python scheduler.py            → inicia agendamento (seg-sex 09:00 Bahia)
#   python scheduler.py --run-now  → executa coleta imediata e sai
# =============================================================================

import sys
import json
import logging
import os
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import config

# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs(config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(config.LOG_DIR, "scheduler.log"),
            encoding="utf-8"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("scheduler")


# =============================================================================
# JOB DE COLETA
# =============================================================================

def job_coleta() -> None:
    """
    Job principal: executa o pipeline completo de ETL.
    Chamado pelo scheduler ou diretamente via --run-now.
    """
    inicio = datetime.now()
    logger.info("=" * 60)
    logger.info(f"INICIANDO COLETA — {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    try:
        from transformer import run_full_pipeline
        resultado = run_full_pipeline(force=True)

        fim = datetime.now()
        duracao = (fim - inicio).total_seconds()
        logger.info(f"COLETA CONCLUÍDA em {duracao:.1f}s")
        for dataset, status in resultado.items():
            icon = "✓" if "ok" in status else ("~" if "cache" in status else "✗")
            logger.info(f"  [{icon}] {dataset}: {status}")

        # Persistir status
        _salvar_status("ok", resultado, inicio, fim)

    except Exception as e:
        logger.error(f"ERRO CRÍTICO na coleta: {e}", exc_info=True)
        _salvar_status("error", {"erro": str(e)}, inicio, datetime.now())


def _salvar_status(
    status: str,
    resultado: dict,
    inicio: datetime,
    fim: datetime,
) -> None:
    """Persiste resultado da coleta em data/last_run.json."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    data = {
        "status":    status,
        "inicio":    inicio.isoformat(),
        "fim":       fim.isoformat(),
        "duracao_s": round((fim - inicio).total_seconds(), 1),
        **resultado,
    }
    with open(config.LAST_RUN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# =============================================================================
# PONTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":

    if "--run-now" in sys.argv:
        # ── Modo manual: executa imediatamente e sai ──────────────────────────
        logger.info("Modo --run-now: executando coleta imediata")
        job_coleta()
        logger.info("Modo --run-now: concluído. Encerrando.")
        sys.exit(0)

    # ── Modo daemon: agendamento automático ───────────────────────────────────
    scheduler = BlockingScheduler(timezone="America/Bahia")

    scheduler.add_job(
        job_coleta,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=9,
            minute=0,
            timezone="America/Bahia",
        ),
        id="coleta_cms",
        name="Coleta CMS Salvador — Dados Parlamentares",
        misfire_grace_time=600,   # tolera atraso de até 10min (ex: máquina hibernando)
        max_instances=1,          # evita sobreposição de execuções
        replace_existing=True,
    )

    logger.info("Scheduler iniciado.")
    logger.info("Próxima execução: segunda a sexta às 09:00 (horário de Bahia/Salvador)")
    logger.info("Pressione Ctrl+C para encerrar.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler encerrado pelo usuário.")
