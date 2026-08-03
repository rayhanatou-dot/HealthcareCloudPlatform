# Healthcare Cloud Platform

## Project Title

Design and Implementation of a Secure, Scalable, and Cost-Efficient Cloud-Based Platform for Healthcare Data Management in Resource-Constrained Environments

## Institution

University of Electronic Science and Technology of China  
School of Information and Software Engineering  
Master in Software Engineering

## Project Description

This project implements a prototype cloud-based healthcare data management platform designed for resource-constrained environments. The platform focuses on secure healthcare data storage, role-based access control, structured patient record management, audit logging, and scalable deployment using open-source technologies.

The prototype is developed as a proof-of-concept system for academic research. It is not intended to replace a full hospital information system. Instead, it demonstrates the core architecture and implementation logic required for secure, scalable, and cost-efficient healthcare data management.

## Main Objectives

- Implement a modular healthcare data management backend.
- Support user authentication and role-based access control.
- Manage structured healthcare records such as patients, encounters, observations, prescriptions, and audit logs.
- Use PostgreSQL for structured healthcare data storage.
- Use MinIO for object storage of clinical files and reports.
- Provide RESTful API endpoints using FastAPI.
- Support testing through Swagger UI and automated test tools.
- Evaluate the prototype using functional, security, and load testing.

## Technology Stack

### Backend
- Python
- FastAPI
- SQLAlchemy
- Alembic
- Pydantic
- JWT authentication
- bcrypt password hashing

### Database
- PostgreSQL

### Object Storage
- MinIO

### Deployment
- Docker
- Docker Compose

### Testing
- Pytest
- Locust
- Swagger UI

### Dataset
- Synthea synthetic healthcare data
- MIMIC-IV Demo for schema reference
- CMS DE-SynPUF for possible scalability testing

## Project Structure

```text
healthcare-cloud-platform/
  backend/
  frontend/
  database/
  scripts/
  tests/
  docs/
  datasets/
  docker-compose.yml
  README.md
  .env.example