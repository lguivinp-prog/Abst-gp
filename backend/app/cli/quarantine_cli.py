import click
import json
import uuid
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.services.quarantine_service import resolve_user, backfill_quarantine_users, QuarantineServiceError, QuarantineAlreadyResolvedError

@click.group()
def quarantine():
    """Manage quarantined users."""
    pass

@quarantine.command()
@click.argument('username')
@click.argument('tenant_id')
@click.argument('resolution_reference')
@click.option('--actor', required=True, help="Username of the administrative actor performing the resolution.")
def resolve(username, tenant_id, resolution_reference, actor):
    """Resolve a quarantined user to a specific tenant."""
    db: Session = SessionLocal()
    try:
        resolve_user(db, username, tenant_id, resolution_reference, actor)
        db.commit()
        click.echo(f"User '{username}' successfully resolved to tenant '{tenant_id}'.")
    except QuarantineAlreadyResolvedError as e:
        db.rollback()
        click.echo(f"Error: {e}", err=True)
    except QuarantineServiceError as e:
        db.rollback()
        click.echo(f"Error: {e}", err=True)
        import sys
        sys.exit(1)
    except Exception as e:
        db.rollback()
        click.echo(f"Unexpected error resolving user: {e}", err=True)
        import sys
        sys.exit(1)
    finally:
        db.close()

@quarantine.command()
@click.option('--actor', required=True, help="Username of the administrative actor performing the backfill.")
@click.option('--operation-id', required=True, help="Unique identifier for idempotency.")
@click.option('--dry-run/--no-dry-run', default=True, help="Run without modifying data.")
def backfill(actor, operation_id, dry_run):
    """Detect and quarantine users without a tenant."""
    db: Session = SessionLocal()
    try:
        result = backfill_quarantine_users(db, actor, operation_id, dry_run=dry_run)
        db.commit()
        
        click.echo(json.dumps(result, indent=2))
        
        if dry_run:
            click.echo("Dry run completed. No data was modified.")
        else:
            click.echo(f"Backfill completed. Quarantined {result['quarantined_count']} users.")
            
    except QuarantineServiceError as e:
        db.rollback()
        click.echo(f"Error: {e}", err=True)
        import sys
        sys.exit(1)
    except Exception as e:
        db.rollback()
        click.echo(f"Unexpected error in backfill: {e}", err=True)
        import sys
        sys.exit(1)
    finally:
        db.close()

if __name__ == '__main__':
    quarantine()
