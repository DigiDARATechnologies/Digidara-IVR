import pymysql
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.database.db import get_db
from app.api.auth import current_admin
from app.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse
from app.services import customer_service

router = APIRouter(dependencies=[Depends(current_admin)])

@router.post(
    "/customers", 
    response_model=CustomerResponse, 
    status_code=status.HTTP_201_CREATED,
    summary="Create a new customer",
    description="Registers a new customer with name, email, and optional phone."
)
def create_customer(
    customer_in: CustomerCreate, 
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    try:
        # Check if email is already registered to provide a cleaner error message
        existing = customer_service.get_customer_by_email(
            db, customer_in.email, admin["organization_id"]
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Customer with email '{customer_in.email}' already exists."
            )
        
        return customer_service.create_customer(
            db, admin["organization_id"], customer_in
        )
    except pymysql.IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database integrity error: {str(e)}"
        )

@router.get(
    "/customers", 
    response_model=List[CustomerResponse],
    summary="Retrieve all customers",
    description="Fetches a list of customers with pagination support."
)
def read_customers(
    skip: int = 0, 
    limit: int = 100, 
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    return customer_service.get_all_customers(
        db, admin["organization_id"], skip=skip, limit=limit
    )

@router.get(
    "/customers/{id}", 
    response_model=CustomerResponse,
    summary="Retrieve a customer by ID",
    description="Fetches details of a specific customer using their unique ID."
)
def read_customer(
    id: int, 
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    customer = customer_service.get_customer_by_id(db, id, admin["organization_id"])
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {id} not found."
        )
    return customer

@router.put(
    "/customers/{id}", 
    response_model=CustomerResponse,
    summary="Update an existing customer",
    description="Modifies specified fields of a customer by ID."
)
def update_customer(
    id: int, 
    customer_in: CustomerUpdate, 
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    # Check if target customer exists
    customer = customer_service.get_customer_by_id(db, id, admin["organization_id"])
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {id} not found."
        )

    # Check for email conflict if the email is being updated
    if customer_in.email and customer_in.email != customer["email"]:
        existing = customer_service.get_customer_by_email(
            db, customer_in.email, admin["organization_id"]
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Customer with email '{customer_in.email}' already exists."
            )

    try:
        updated = customer_service.update_customer(
            db, id, admin["organization_id"], customer_in
        )
        return updated
    except pymysql.IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database integrity error: {str(e)}"
        )

@router.delete(
    "/customers/{id}",
    summary="Delete a customer",
    description="Permanently deletes a customer record from the database."
)
def delete_customer(
    id: int, 
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    success = customer_service.delete_customer(db, id, admin["organization_id"])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {id} not found."
        )
    return {"message": f"Customer with ID {id} deleted successfully."}
