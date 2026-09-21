from pydantic import BaseModel, Field
from typing import Optional

class CustomerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Customer name")
    email: str = Field(
        ..., 
        pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        description="Customer email address"
    )
    phone: Optional[str] = Field(None, description="Customer phone number")
    language: Optional[str] = Field(None, description="Customer preferred language (e.g. 'english' or 'tamil')")
    investigated_course: Optional[str] = Field(None, description="Course name investigated by customer")
    internship_or_course: Optional[str] = Field(None, description="Whether it is an internship or a course")
    course_duration: Optional[str] = Field(None, description="Duration of the course")
    customer_status: Optional[str] = Field(None, description="Current customer/lead status")

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Customer name")
    email: Optional[str] = Field(
        None, 
        pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        description="Customer email address"
    )
    phone: Optional[str] = Field(None, description="Customer phone number")
    language: Optional[str] = Field(None, description="Customer preferred language (e.g. 'english' or 'tamil')")
    investigated_course: Optional[str] = Field(None, description="Course name investigated by customer")
    internship_or_course: Optional[str] = Field(None, description="Whether it is an internship or a course")
    course_duration: Optional[str] = Field(None, description="Duration of the course")
    customer_status: Optional[str] = Field(None, description="Current customer/lead status")

class CustomerResponse(CustomerBase):
    id: int
    created_at: str

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "name": "Jane Doe",
                "email": "jane.doe@example.com",
                "phone": "+1234567890",
                "language": "english",
                "created_at": "2026-06-03 00:00:00"
            }
        }
