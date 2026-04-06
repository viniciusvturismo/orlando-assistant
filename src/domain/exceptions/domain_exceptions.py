class OrlandoBaseException(Exception):
    pass


class GroupNotFound(OrlandoBaseException):
    def __init__(self, group_id: str):
        super().__init__(f"Group not found: {group_id}")


class GroupSetupIncomplete(OrlandoBaseException):
    def __init__(self, group_id: str, next_step: str):
        self.next_step = next_step
        super().__init__(f"Group {group_id} setup incomplete. Next step: {next_step}")


class NoContextActive(OrlandoBaseException):
    def __init__(self, group_id: str):
        super().__init__(f"No active context for group: {group_id}")


class NoEligibleAttractions(OrlandoBaseException):
    def __init__(self, reason: str = ""):
        super().__init__(f"No eligible attractions found. {reason}")


class AttractionNotFound(OrlandoBaseException):
    def __init__(self, attraction_id: str):
        super().__init__(f"Attraction not found: {attraction_id}")


class ContextExpired(OrlandoBaseException):
    def __init__(self, context_id: str):
        super().__init__(f"Context expired: {context_id}")
