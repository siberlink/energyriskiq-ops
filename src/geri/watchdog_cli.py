"""Independent scheduler entry point; no customer delivery configuration."""
from src.geri.integrity_schema import migrate
from src.geri.job_health import watchdog

if __name__ == "__main__":
    migrate()
    status = watchdog()
    print(f"GERI watchdog: {status}")
    raise SystemExit(1 if status == "admin_alert" else 0)
