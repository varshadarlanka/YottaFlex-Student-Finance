"""
backend/generators/students.py
================================
Generates synthetic student records.

Design
------
* Names are constructed from fixed first-name and last-name pools.
  Both pools have sufficient size that 10,000 unique combinations
  are achievable without repetition.
* Emails are generated as: {first}.{last}.{n}@institution.edu
  where n is the student sequence number — guarantees uniqueness.
* All personal data is synthetic and does not correspond to real individuals.
* Phone numbers follow the Indian mobile format: +91 {10 digits starting 6-9}.
* Date of birth is chosen randomly from a realistic student age range (17–30).
* Addresses use the INDIAN_CITIES list from config.
* Student status is assigned via weighted random using config weights.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date
from typing import Any, Dict, List

from backend.config import GenerationConfig, GENDERS, GENDER_WEIGHTS, INDIAN_CITIES
from backend.id_generator import IDGenerator
from backend.seed_manager import SeededRandom
from backend.validators import validate_student_row

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Name pools — large enough for 10,000 unique students.
# These are synthetic; not real personal data.
# ---------------------------------------------------------------------------
_FIRST_NAMES = [
    "Aarav", "Aakash", "Abhishek", "Aditya", "Ajay", "Akash", "Amit", "Anand",
    "Anjali", "Ankit", "Ankita", "Anushka", "Arjun", "Aryan", "Ashish", "Ashwin",
    "Bhavna", "Chandan", "Deepak", "Deepika", "Dev", "Dhruv", "Divya", "Gaurav",
    "Geeta", "Girish", "Harish", "Harshit", "Heena", "Himanshu", "Ishaan", "Ishita",
    "Jaya", "Jayesh", "Karan", "Kavita", "Kishore", "Komal", "Krishna", "Kunal",
    "Lalit", "Lakshmi", "Mahesh", "Manish", "Manisha", "Meena", "Meera", "Mohit",
    "Monika", "Mukesh", "Naman", "Nandita", "Narayan", "Neha", "Nikhil", "Nisha",
    "Nitesh", "Niti", "Omkar", "Pallavi", "Pankaj", "Parth", "Pooja", "Pradeep",
    "Pragati", "Prashant", "Pratik", "Praveen", "Preeti", "Preethi", "Priya",
    "Rahul", "Rajan", "Rajesh", "Rakesh", "Ramesh", "Ravi", "Renu", "Ritesh",
    "Rohit", "Roshan", "Sachin", "Sagar", "Sahil", "Sanjay", "Sanjeev", "Sarika",
    "Satish", "Seema", "Shailesh", "Shivam", "Shubham", "Sneha", "Sohan", "Sudhir",
    "Sunil", "Sunita", "Suresh", "Swati", "Tarun", "Tushar", "Uday", "Usha",
    "Vaibhav", "Vandana", "Vijay", "Vikram", "Vikas", "Vinay", "Vipul", "Vishal",
    "Vivek", "Yash", "Yogesh", "Zara", "Zoya", "Akshay", "Amrita", "Bala",
    "Chitra", "Damodar", "Ekta", "Farhan", "Gagan", "Harsh", "Indira", "Jatin",
    "Karishma", "Leela", "Madhu", "Neeraj", "Omprakash", "Piyush", "Queenie",
    "Rajani", "Sheela", "Trilok", "Upendra", "Varun", "Wasim", "Xena", "Yamini",
]

_LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Singh", "Kumar", "Patel", "Mehta", "Joshi",
    "Nair", "Reddy", "Rao", "Iyer", "Pillai", "Menon", "Bhat", "Kaur", "Shah",
    "Malhotra", "Chopra", "Khanna", "Agarwal", "Bansal", "Garg", "Mittal",
    "Saxena", "Srivastava", "Tiwari", "Pandey", "Mishra", "Shukla", "Chauhan",
    "Yadav", "Maurya", "Rajput", "Thakur", "Bose", "Chatterjee", "Mukherjee",
    "Ghosh", "Das", "Sen", "Roy", "Dey", "Mandal", "Ghosh", "Biswas", "Mitra",
    "Choudhury", "Bhattacharya", "Datta", "Naik", "Hegde", "Gowda", "Shetty",
    "Kamath", "Bhatt", "Kulkarni", "Desai", "Patil", "Pawar", "Shinde", "Jadhav",
    "Mane", "Sawant", "Rane", "Parab", "Raut", "Gaikwad", "Sutar", "Avhad",
    "Dubey", "Tripathi", "Keshari", "Bajpai", "Chaturvedi", "Awasthi", "Katiyar",
    "Khan", "Ansari", "Siddiqui", "Qureshi", "Sheikh", "Malik", "Mirza", "Hashmi",
    "Nanda", "Ahuja", "Arora", "Bedi", "Dhillon", "Sodhi", "Grover", "Taneja",
    "Sethi", "Kapoor", "Mehra", "Bajaj", "Birla", "Dalmia", "Kejriwal",
    "Adani", "Mundra", "Rathi", "Jain", "Lodha", "Oberoi", "Anand", "Bakshi",
]


class StudentGenerator:
    """
    Generates synthetic student records.

    Parameters
    ----------
    config : GenerationConfig
    rng : SeededRandom
        Child RNG forked from the main RNG with label "students".
    id_gen : IDGenerator
        Shared ID generator.
    """

    def __init__(
        self,
        config: GenerationConfig,
        rng: SeededRandom,
        id_gen: IDGenerator,
    ) -> None:
        self._config = config
        self._rng = rng
        self._id_gen = id_gen
        self._students: List[Dict[str, Any]] = []

    def build(self) -> List[Dict[str, Any]]:
        """
        Generate all student dicts in memory.

        Returns
        -------
        list[dict]
        """
        self._students = []
        n = self._config.num_students
        rng = self._rng

        status_items = list(self._config.student_status_weights.keys())
        status_weights = list(self._config.student_status_weights.values())

        reference_date = date(self._config.base_year, 1, 1)

        for i in range(n):
            code = self._id_gen.student_code()

            first = rng.choice(_FIRST_NAMES)
            last = rng.choice(_LAST_NAMES)

            # email: unique by incorporating student sequence number
            seq = self._id_gen.current("STU")
            email = f"{first.lower()}.{last.lower()}.{seq:06d}@institution.edu"

            dob = rng.random_date_of_birth(min_age=17, max_age=30, reference=reference_date)

            gender = rng.choices(GENDERS, weights=GENDER_WEIGHTS, k=1)[0]

            status = rng.weighted_choice(status_items, status_weights)

            city_info = rng.choice(INDIAN_CITIES)
            city, state, pin_prefix = city_info
            pincode = f"{pin_prefix}{rng.randint(100, 999):03d}"

            # Phone: +91 followed by 10 digits starting 6-9
            first_digit = rng.choice(["6", "7", "8", "9"])
            rest_digits = "".join(str(rng.randint(0, 9)) for _ in range(9))
            phone = f"+91{first_digit}{rest_digits}"

            # Admission date: within the term window
            admission_year = self._config.base_year + rng.randint(0, max(0, self._config.num_terms // 2 - 1))
            admission_date = f"{admission_year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"

            row: Dict[str, Any] = {
                "student_code":  code,
                "first_name":    first,
                "last_name":     last,
                "date_of_birth": dob.isoformat(),
                "gender":        gender,
                "email":         email,
                "phone":         phone,
                "address_line1": f"{rng.randint(1, 999)}, {rng.choice(['MG Road', 'Park Street', 'Station Road', 'Main Street', 'Gandhi Nagar'])}",
                "address_line2": None,
                "city":          city,
                "state":         state,
                "pincode":       pincode,
                "status":        status,
            }
            validate_student_row(row)
            self._students.append(row)

        logger.debug("Built %d student records.", len(self._students))
        return self._students

    def insert(self, conn: sqlite3.Connection, batch_size: int = 500) -> Dict[str, int]:
        """
        Batch-insert students into the database.

        Uses INSERT OR IGNORE so that reruns skip existing records.
        Returns stats dict with inserted and skipped counts.
        """
        if not self._students:
            self.build()

        stats = {"inserted": 0, "skipped": 0}
        batch: List[Dict[str, Any]] = []

        def _flush(b: List[Dict[str, Any]]) -> None:
            conn.executemany(
                """INSERT OR IGNORE INTO Students
                       (student_code, first_name, last_name, date_of_birth,
                        gender, email, phone, address_line1, address_line2,
                        city, state, pincode, status)
                   VALUES (:student_code, :first_name, :last_name, :date_of_birth,
                           :gender, :email, :phone, :address_line1, :address_line2,
                           :city, :state, :pincode, :status)""",
                b,
            )

        for row in self._students:
            batch.append(row)
            if len(batch) >= batch_size:
                _flush(batch)
                batch.clear()

        if batch:
            _flush(batch)

        # Count actual inserts
        total_in_db = conn.execute("SELECT COUNT(*) FROM Students").fetchone()[0]
        stats["inserted"] = min(len(self._students), total_in_db)
        stats["skipped"] = len(self._students) - stats["inserted"]

        logger.info(
            "Students: %d records processed, ~%d in DB, %d skipped.",
            len(self._students),
            total_in_db,
            stats["skipped"],
        )
        return stats

    def get_students(self) -> List[Dict[str, Any]]:
        if not self._students:
            self.build()
        return self._students
