"""The AI Front Desk agent and its ten tools (spec 05 §4, §5.2).

Every tool goes through the API's internal routes, which enforce the scope, the identity gate and
the time window (§5.1). The model never sees data outside what these tools return.
"""

from typing import Any

from livekit.agents import Agent, RunContext, function_tool

from bayflow_agent.internal_api import InternalApi
from bayflow_agent.prompts import system_prompt


class FrontDeskAgent(Agent):
    def __init__(self, api: InternalApi, *, shop_name: str, shop_city: str) -> None:
        super().__init__(instructions=system_prompt(shop_name, shop_city))
        self._api = api
        self.ended = False

    @function_tool()
    async def verify_caller(
        self,
        context: RunContext[Any],
        name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        booking_reference: str | None = None,
    ) -> dict[str, Any]:
        """Verify who is calling, with at least one detail the caller gave. Call this before
        sharing any booking information.

        Args:
            name: The caller's name as they said it.
            phone: Their phone number, digits only if possible.
            email: Their e-mail address written normally, e.g. ahmed@mail.com.
            booking_reference: A booking reference such as BF-7K2M9Q.
        """
        return await self._api.verify_caller(
            name=name, phone=phone, email=email, booking_reference=booking_reference
        )

    @function_tool()
    async def get_shop_info(self, context: RunContext[Any]) -> dict[str, Any]:
        """The shop's address, phone, working hours and services. No verification needed."""
        return await self._api.get_shop()

    @function_tool()
    async def get_my_bookings(self, context: RunContext[Any]) -> dict[str, Any]:
        """The verified caller's bookings at this shop, newest first."""
        return await self._api.get_bookings()

    @function_tool()
    async def get_booking_status(
        self, context: RunContext[Any], booking_reference: str
    ) -> dict[str, Any]:
        """Status, appointment time and estimate total of one of the caller's bookings.

        Args:
            booking_reference: Booking reference such as BF-7K2M9Q.
        """
        return await self._api.get_booking(booking_reference)

    @function_tool()
    async def get_estimate(
        self, context: RunContext[Any], booking_reference: str
    ) -> dict[str, Any]:
        """The latest estimate the customer can see for one of their bookings.

        Args:
            booking_reference: Booking reference such as BF-7K2M9Q.
        """
        return await self._api.get_estimate(booking_reference)

    @function_tool()
    async def get_available_slots(
        self, context: RunContext[Any], date: str, days: int = 1
    ) -> dict[str, Any]:
        """Free appointment times at this shop.

        Args:
            date: The first day to look at, YYYY-MM-DD in the shop's time.
            days: How many days to look at, 1 to 7.
        """
        return await self._api.get_slots(date, max(1, min(days, 7)))

    @function_tool()
    async def request_reschedule(
        self,
        context: RunContext[Any],
        booking_reference: str,
        preferred_starts: list[str],
        note: str | None = None,
    ) -> dict[str, Any]:
        """Pass a reschedule request to the service advisor. The booking is NOT moved.

        Args:
            booking_reference: The booking to move, e.g. BF-7K2M9Q.
            preferred_starts: One to three `start` values from get_available_slots.
            note: Anything the caller added.
        """
        created = await self._api.create_task(
            {
                "kind": "RESCHEDULE_REQUEST",
                "booking_reference": booking_reference,
                "preferred_starts": preferred_starts[:3],
                "description": note,
            }
        )
        return {**created, "message": "The service advisor will confirm a new time."}

    @function_tool()
    async def request_callback(
        self, context: RunContext[Any], topic: str, description: str | None = None
    ) -> dict[str, Any]:
        """Ask a service advisor to call the customer back. Works without verification.

        Args:
            topic: A few words, e.g. "the estimate".
            description: What the caller wants, in one or two sentences.
        """
        created = await self._api.create_task(
            {"kind": "CALLBACK", "topic": topic[:60], "description": description}
        )
        return {**created, "message": "An advisor will call back."}

    @function_tool()
    async def escalate_to_human(
        self, context: RunContext[Any], reason: str, safety_concern: bool = False
    ) -> dict[str, Any]:
        """Flag the call as urgent for an advisor: the caller asked for a person, is upset, or
        mentioned a safety problem.

        Args:
            reason: A few words on why.
            safety_concern: True for brakes, smoke, fire, fuel leak, overheating, steering,
                accident, tow, stranded or breakdown.
        """
        created = await self._api.create_task(
            {"kind": "ESCALATION", "topic": reason, "safety_concern": safety_concern}
        )
        return {**created, "message": "Flagged as urgent; an advisor will call back soon."}

    @function_tool()
    async def end_call(self, context: RunContext[Any]) -> None:
        """End the call. Use only after you have said goodbye."""
        await context.wait_for_playout()  # let the goodbye finish playing
        self.ended = True
        await self._api.end_call()  # the API deletes the room
