"""Fixed limits of the calls module (spec 05 §3.5, §8.3, §11.3, `modules/calls.md`).

Constants, not environment variables: both the API and the agent read `AI_MAX_CALL_SECONDS` from the
`/session` response, so the two sides always agree.
"""

from typing import Final

AGENT_NAME: Final = "bayflow-front-desk"  # D58: explicit dispatch only
ROOM_PREFIX: Final = "call-"  # rooms are `call-<call_id>` (D57)
IDENTITY_PREFIX: Final = "u_"  # human participants are `u_<user_id>`

AI_JOIN_TIMEOUT_SECONDS: Final = 10  # A4: no `/session` within this → agent unavailable
CALL_MAX_SECONDS: Final = 900  # C6 by the sweeper for a human call
AI_MAX_CALL_SECONDS: Final = 300  # the agent wraps up at 270 s
AI_MAX_BACKSTOP_SECONDS: Final = AI_MAX_CALL_SECONDS + 60  # sweeper backstop (A3)
SUMMARY_GRACE_SECONDS: Final = 180  # A6: no summary this long after the leg ended
SUMMARY_WINDOW_SECONDS: Final = 600  # `/summary` accepted until ai_ended_at + 10 min
SWEEP_INTERVAL_SECONDS: Final = 5.0

ROOM_EMPTY_TIMEOUT_SECONDS: Final = 60
ROOM_DEPARTURE_TIMEOUT_SECONDS: Final = 10
ROOM_MAX_PARTICIPANTS: Final = 3
TOKEN_TTL_SECONDS: Final = 120  # LiveKit join tokens

START_LIMIT: Final = 5  # call starts per caller ...
START_WINDOW_SECONDS: Final = 600  # ... per 10 minutes (D69)

MAX_IDENTITY_ATTEMPTS: Final = 3
MAX_TRANSCRIPT_ENTRIES: Final = 300
MAX_TRANSCRIPT_BYTES: Final = 200_000
MAX_AGENT_BOOKINGS: Final = 10
MAX_SLOTS: Final = 12
MAX_PREFERRED_STARTS: Final = 3
