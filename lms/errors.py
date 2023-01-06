from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from lms.models import LibraryUser, Loan


class Error(Exception):
    """Base class for other exceptions"""

    pass


class APINotFoundError(Error):
    """Raised when an object is not found from the API"""

    def __init__(self, object_id, object_type):
        self.message = f"{object_id} -> {object_type} not found from API"
        super().__init__(self.message)


class ObjectExistsError(Error):
    """Raised when an object with a certain ID already exists"""

    def __init__(self, object_id, object_type):
        self.message = f"{object_id} -> {object_type} already exists"
        super().__init__(self.message)


class MaxLoansError(Error):
    """Raised when a user already has the maximum number of loans out"""

    def __init__(self, user: LibraryUser):
        self.message = f"{user.username} already has {user.loans_allowed} out of {user.loans_allowed} books out"
        super().__init__(self.message)


class MaxRenewalsError(Error):
    """Raised when a user has already renewed a loan the maximum amount of times
    allowed """

    def __init__(self, loan: Loan):
        self.message = f"{loan.book} has already been renewed the book out of " \
                       f"{loan.renewals} out of {loan.renewals} times "
        super().__init__(self.message)
