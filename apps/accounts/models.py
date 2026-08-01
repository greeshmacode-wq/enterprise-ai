from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid

class User(AbstractUser):
    class RoleChoices(models.TextChoices):
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manager"
        EMPLOYEE = "employee", "Employee"

    uuid= models.UUIDField(unique=True,default=uuid.uuid4,editable=False)
    email = models.EmailField(max_length=120,unique=True)
    employee_id = models.CharField(max_length=20, unique=True,blank=True,null=True)
    department= models.CharField(max_length=120,blank=True)
    designation = models.CharField(max_length=120,blank=True)
    role = models.CharField(max_length=20,choices=RoleChoices.choices,
        default=RoleChoices.EMPLOYEE,
    )
    def __str__(self):
        return self.get_full_name() or self.username
    
    class Meta:
        db_table = "users"
        ordering = ["username"] #Whenever Django fetches users, they will be ordered by username [User.objects.all()]