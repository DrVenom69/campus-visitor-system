# Database Model

The application uses six core tables. `HostAssignment` has two foreign keys to `User`: one for the assigned host and one for the staff member who made the assignment.

```mermaid
erDiagram
    User ||--o{ HostAssignment : hosts
    User ||--o{ HostAssignment : assigns
    User ||--o{ CheckInOut : performs
    Visitor ||--o{ VisitRequest : submits
    VisitRequest ||--o| HostAssignment : receives
    VisitRequest ||--o| GatePass : creates
    GatePass ||--o{ CheckInOut : records

    User {
        int id PK
        string name
        string email UK
        string password_hash
        string role
        boolean is_active
        datetime created_at
    }
    Visitor {
        int id PK
        string full_name
        string email
        string phone
        string organization
        datetime created_at
    }
    VisitRequest {
        int id PK
        string request_id UK
        int visitor_id FK
        string purpose
        string host_requested
        date visit_date
        string status
        int reviewed_by_id FK
        datetime reviewed_at
        datetime created_at
    }
    HostAssignment {
        int id PK
        int visit_request_id FK
        int host_id FK
        int assigned_by_id FK
        datetime assigned_at
    }
    GatePass {
        int id PK
        int visit_request_id FK
        string pass_code UK
        datetime issued_at
        datetime valid_until
        boolean is_active
    }
    CheckInOut {
        int id PK
        int gate_pass_id FK
        datetime check_in_time
        datetime check_out_time
        int security_id FK
    }
```

`VisitRequest` may exist without a `GatePass` while it is pending or rejected. A gate pass may exist without any `CheckInOut` rows until security scans it. Each check-in record belongs to a gate pass and stores the optional matching check-out time.
