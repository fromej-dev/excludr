from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, select

from .models import Criterion, CriterionCreate, CriterionUpdate, CriterionType
from ...core.database import SessionDep


class CriterionService:
    """Service class for managing Criterion-related operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_criteria_for_project(self, project_id: int):
        """Get all criteria for a project ordered by type and order."""
        return (
            select(Criterion)
            .where(Criterion.project_id == project_id)
            .order_by(Criterion.type, Criterion.order)
        )

    def get_active_criteria_for_project(self, project_id: int):
        """Get only active criteria for a project."""
        return (
            select(Criterion)
            .where(
                Criterion.project_id == project_id,
                Criterion.is_active == True,  # noqa: E712
            )
            .order_by(Criterion.type, Criterion.order)
        )

    def get_criterion_by_id(self, criterion_id: int) -> Criterion | None:
        """Get a criterion by its ID."""
        return self.session.exec(
            select(Criterion).where(Criterion.id == criterion_id)
        ).first()

    def get_next_order(self, project_id: int, criterion_type: CriterionType) -> int:
        """Get the next order number for a criterion type in a project."""
        result = self.session.exec(
            select(Criterion)
            .where(Criterion.project_id == project_id, Criterion.type == criterion_type)
            .order_by(Criterion.order.desc())
        ).first()
        return (result.order + 1) if result else 0

    def create_criterion(self, project_id: int, data: CriterionCreate) -> Criterion:
        """Create a new criterion for a project."""
        criterion = Criterion(**data.model_dump())
        criterion.project_id = project_id

        # Auto-assign order if not specified or default
        if data.order is None or data.order == 0:
            criterion.order = self.get_next_order(project_id, data.type)

        self.session.add(criterion)
        self.session.commit()
        self.session.refresh(criterion)
        return criterion

    def update_criterion(
        self, criterion: Criterion, data: CriterionUpdate
    ) -> Criterion:
        """Update an existing criterion."""
        criterion.sqlmodel_update(
            data.model_dump(
                exclude_unset=True, exclude_defaults=True, exclude_none=True
            )
        )
        self.session.add(criterion)
        self.session.commit()
        self.session.refresh(criterion)
        return criterion

    def delete_criterion(self, criterion: Criterion) -> None:
        """Delete a criterion."""
        self.session.delete(criterion)
        self.session.commit()

    def reorder_criteria(
        self, project_id: int, criterion_ids: list[int]
    ) -> list[Criterion]:
        """Reorder criteria based on the provided list of IDs."""
        criteria = []
        for order, criterion_id in enumerate(criterion_ids):
            criterion = self.get_criterion_by_id(criterion_id)
            if criterion and criterion.project_id == project_id:
                criterion.order = order
                self.session.add(criterion)
                criteria.append(criterion)
        self.session.commit()
        for c in criteria:
            self.session.refresh(c)
        return criteria


def get_criterion_service(session: SessionDep) -> CriterionService:
    """Dependency injection function to get CriterionService instance."""
    return CriterionService(session=session)


CriterionServiceDep = Annotated[CriterionService, Depends(get_criterion_service)]
