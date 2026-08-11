"""The resolved application: configuration and the stores built from it.

Assembled once at startup in `server.main()` and handed to the router. It is
frozen and passed, never reached for — no module holds it. The Session it
carries owns the live conversation state, so nothing on the conversation path
is a module global. A flow still receives only what it needs, through `Deps`.
"""

from dataclasses import dataclass

from database import Database
from js8_db import Js8Database
from session import Session
from settings import Config


@dataclass(frozen=True)
class Runtime:
    config: Config
    database: Database
    js8_database: Js8Database
    session: Session
