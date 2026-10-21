"""Registers every module's ORM models on `Base.metadata`.

Imported by `app.main` and by Alembic's `env.py`. Foreign keys are declared by table name across
modules (spec 01 rule 2), so every referenced table must be registered before the first flush
or migration autogenerate. Add a module here when it gains a `models.py`.
"""

from sqlalchemy import MetaData

from app.core.database import Base
from app.modules.ai import models as ai_models
from app.modules.audit import models as audit_models
from app.modules.bookings import models as bookings_models
from app.modules.calls import models as calls_models
from app.modules.estimates import models as estimates_models
from app.modules.identity import models as identity_models
from app.modules.inventory import models as inventory_models
from app.modules.notifications import models as notifications_models
from app.modules.qc import models as qc_models
from app.modules.scheduling import models as scheduling_models
from app.modules.shops import models as shops_models

MODEL_MODULES = (
    identity_models,
    shops_models,
    scheduling_models,
    bookings_models,
    estimates_models,
    inventory_models,
    qc_models,
    notifications_models,
    audit_models,
    calls_models,
    ai_models,
)

metadata: MetaData = Base.metadata
