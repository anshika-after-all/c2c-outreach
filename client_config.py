"""PDF sections 3 and 8.1 — candidates, roles, and keyword lists.

Add a person by copying the jane_doe blocks into CLIENTS and CANDIDATE_ROLES.
The dict key must match in both places. Put their resume under clients/.
"""

from pathlib import Path

from settings import ROOT

# Replace Jane before a live send. example.com is a safe placeholder.
CLIENTS = {
    "jane_doe": {
        "name": "Jane Doe",
        "email": "janedoe@example.com",
        "lead_email": "",
        "phone": "555-019-2834",
        "linkedin": "https://www.linkedin.com/in/janedoe",
        "location": "Dallas, TX",
        "relocation": "Yes",
        "work_auth": "H1B",
        "availability": "Immediate",
        "experience": "5+ Years",
        "resume_candidates": ["clients/jane_doe_resume.docx"],
    }
}

CANDIDATE_ROLES = {
    "jane_doe": {
        "primary_role": "Java Developer",
        "search_roles": ["Java Developer", "Backend Engineer"],
        "exclusion_keywords": ["hotlist", "fulltime", "available consultants", "bench"],
    }
}

# A post that names any of these is dropped, even if it also names a US city.
NON_USA = [
    "india", "pune", "noida", "gurgaon", "gurugram", "hyderabad", "bangalore",
    "bengaluru", "chennai", "mumbai", "kolkata", "ahmedabad", "canada", "toronto",
    "vancouver", "united kingdom", "london", "europe", "germany", "poland",
    "mexico", "philippines", "pakistan", "bangladesh", "offshore",
]

USA_CITIES = [
    "dallas", "austin", "houston", "new york", "nyc", "san francisco", "seattle",
    "chicago", "atlanta", "boston", "denver", "phoenix", "charlotte", "raleigh",
    "miami", "tampa", "orlando", "los angeles", "san jose", "irvine", "plano",
    "irving", "washington",
]

# Longer phrases come first so "Spring Boot" wins over "Spring".
JD_KEYWORDS = [
    "Spring Boot", "Spring", "Hibernate", "Microservices", "REST", "Kafka",
    "PostgreSQL", "MySQL", "Oracle", "MongoDB", "AWS", "Azure", "GCP", "Docker",
    "Kubernetes", "Python", "Django", "Flask", "FastAPI", "Pandas", "Spark",
    "Hadoop", "SQL", "Airflow", "Tableau", "Power BI", "TensorFlow", "PyTorch",
    "Scikit-learn", "React", "Angular", "Node.js", "JavaScript", "TypeScript",
    "Next.js", "Java", ".NET", "C#", "ASP.NET", "Golang", "Scala", "Salesforce",
    "Apex", "DevOps", "CI/CD", "Jenkins", "Terraform", "Ansible", "Linux",
    "Redis", "Elasticsearch", "RabbitMQ", "GraphQL", "JUnit", "Maven", "Gradle",
    "Snowflake", "Databricks", "Selenium", "Playwright", "HTML", "CSS", "Git",
]


def candidate(key: str) -> dict:
    # One dict so senders do not have to look in two maps.
    if key not in CLIENTS or key not in CANDIDATE_ROLES:
        raise KeyError(f"Unknown candidate: {key}")
    return {"key": key, **CLIENTS[key], **CANDIDATE_ROLES[key]}


def resume_path(key: str) -> Path:
    # First file that exists wins, so a pdf can sit in front of a docx.
    for relative in CLIENTS[key]["resume_candidates"]:
        path = ROOT / relative
        if path.exists():
            return path
    raise FileNotFoundError(f"No resume file for {key}. Checked resume_candidates.")
