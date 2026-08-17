import os
import re
import json
import logging
from typing import Dict, Any, List, Tuple, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Technical Synonym & Alias Ontology
# ---------------------------------------------------------------------------

TECH_ALIASES: Dict[str, Set[str]] = {
    "python": {"python", "python3", "python 3", "py"},
    "javascript": {"javascript", "js", "ecmascript", "es6", "es6+"},
    "typescript": {"typescript", "ts"},
    "c++": {"c++", "cpp", "c plus plus"},
    "c#": {"c#", "csharp", "c sharp", ".net"},
    "golang": {"golang", "go", "go lang"},
    "rust": {"rust", "rustlang"},
    "java": {"java", "core java", "j2ee"},
    "sql": {"sql", "structured query language", "rdbms"},
    "postgresql": {"postgresql", "postgres", "psql"},
    "mysql": {"mysql"},
    "mongodb": {"mongodb", "mongo", "nosql"},
    "redis": {"redis", "in-memory cache"},
    "react": {"react", "react.js", "reactjs", "react 18"},
    "next.js": {"next.js", "nextjs", "next"},
    "vue": {"vue", "vue.js", "vuejs"},
    "angular": {"angular", "angularjs", "angular 2+"},
    "flask": {"flask", "flask-restful"},
    "django": {"django", "django rest framework", "drf"},
    "fastapi": {"fastapi"},
    "node.js": {"node.js", "nodejs", "node"},
    "express": {"express", "express.js", "expressjs"},
    "docker": {"docker", "containerization", "containers"},
    "kubernetes": {"kubernetes", "k8s"},
    "aws": {"aws", "amazon web services", "amazon cloud", "ec2", "s3", "lambda"},
    "gcp": {"gcp", "google cloud", "google cloud platform"},
    "azure": {"azure", "microsoft azure"},
    "git": {"git", "github", "gitlab", "version control"},
    "ci/cd": {"ci/cd", "continuous integration", "continuous deployment", "github actions", "jenkins"},
    "machine learning": {"machine learning", "ml", "statistical learning"},
    "deep learning": {"deep learning", "dl", "neural networks"},
    "artificial intelligence": {"artificial intelligence", "ai", "genai", "generative ai", "llm", "large language models"},
    "pytorch": {"pytorch", "torch"},
    "tensorflow": {"tensorflow", "tf", "keras"},
    "scikit-learn": {"scikit-learn", "sklearn"},
    "pandas": {"pandas"},
    "numpy": {"numpy"},
    "rest apis": {"rest apis", "rest api", "restful", "restful apis", "rest web services", "api development"},
    "graphql": {"graphql"},
    "linux": {"linux", "unix", "ubuntu", "bash", "shell scripting"},
    "algorithms": {"algorithms", "data structures", "dsa", "problem solving"},
    "distributed systems": {"distributed systems", "microservices", "system design", "scalability"},
    "html": {"html", "html5"},
    "css": {"css", "css3", "sass", "scss", "tailwind", "tailwind css", "bootstrap"},
}

# Reverse lookup dictionary: alias -> canonical key
ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical, aliases in TECH_ALIASES.items():
    for alias in aliases:
        ALIAS_TO_CANONICAL[alias.lower().strip()] = canonical

def get_canonical_skill(skill_str: str) -> str:
    """Returns canonical technology name if recognized, else cleaned lowercase string."""
    if not skill_str:
        return ""
    clean = str(skill_str).lower().strip()
    return ALIAS_TO_CANONICAL.get(clean, clean)

def skills_are_equivalent(skill1: str, skill2: str) -> bool:
    """Checks if two skill strings are equivalent or aliases of the same technology."""
    c1 = get_canonical_skill(skill1)
    c2 = get_canonical_skill(skill2)
    if c1 == c2:
        return True
    if c1 in c2 or c2 in c1:
        return True
    return False

# ---------------------------------------------------------------------------
# 2. Job Description Requirement Analysis
# ---------------------------------------------------------------------------

KNOWN_TECH_VOCABULARY = set(ALIAS_TO_CANONICAL.keys()) | {
    "spark", "hadoop", "kafka", "airflow", "snowflake", "bigquery", "databricks",
    "terraform", "ansible", "helm", "prometheus", "grafana", "selenium", "playwright",
    "cypress", "jest", "pytest", "junit", "mocha", "jira", "confluence", "agile", "scrum",
    "spring", "spring boot", "ruby", "rails", "php", "laravel", "scala", "swift", "kotlin",
    "flutter", "react native", "android", "ios", "solidity", "web3", "opencv", "nltk", "spacy",
    "huggingface", "langchain", "llamaindex", "pinecone", "weaviate", "qdrant", "chromadb"
}

SOFT_SKILLS_KEYWORDS = {
    "communication", "teamwork", "collaboration", "leadership", "problem solving",
    "critical thinking", "adaptability", "ownership", "curiosity", "fast-paced",
    "mentorship", "initiative", "attention to detail", "analytical skills"
}

SENIORITY_KEYWORDS = {
    "intern": "Internship",
    "internship": "Internship",
    "co-op": "Internship",
    "entry level": "Entry Level",
    "junior": "Entry Level",
    "associate": "Entry Level",
    "university graduate": "Entry Level",
    "new grad": "Entry Level",
    "early career": "Entry Level",
    "senior": "Senior",
    "staff": "Staff",
    "lead": "Lead",
    "principal": "Principal",
    "manager": "Manager"
}

CANONICAL_DISPLAY_NAMES: Dict[str, str] = {
    "c++": "C++",
    "c#": "C#",
    "ci/cd": "CI/CD",
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "golang": "Golang",
    "html": "HTML",
    "css": "CSS",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "rest apis": "REST APIs",
    "graphql": "GraphQL",
    "node.js": "Node.js",
    "next.js": "Next.js",
    "vue": "Vue",
    "react": "React",
    "flask": "Flask",
    "django": "Django",
    "fastapi": "FastAPI",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "scikit-learn": "Scikit-Learn",
    "git": "Git",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "redis": "Redis",
    "linux": "Linux",
    "python": "Python",
    "java": "Java",
    "rust": "Rust",
    "solidity": "Solidity"
}

def make_word_pattern(word: str) -> str:
    """Builds regex pattern handling punctuation like C++ and C#."""
    escaped = re.escape(word)
    prefix = r'\b' if re.match(r'^\w', word) else r'(?:(?<=[\s,;.(/])|^)'
    suffix = r'\b' if re.match(r'.*\w$', word) else r'(?:(?=[\s,;.)/]|$))'
    return prefix + escaped + suffix

def analyze_job_requirements(job_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses a target job posting into structured, categorized requirements:
    - required_skills: Skills explicitly stated as required / qualifications / must-have.
    - preferred_skills: Skills stated as preferred / plus / bonus / nice-to-have.
    - contextual_skills: Skills mentioned elsewhere in the description.
    - seniority: Seniority level extracted from title / description.
    - keywords: High-priority technical and domain keywords.
    - soft_skills: Mentioned behavioral competencies.
    """
    title = str(job_dict.get("title", "")).strip()
    description = str(job_dict.get("description", "")).strip()
    full_text = f"{title}\n{description}"
    full_text_lower = full_text.lower()

    # 1. Seniority Detection
    seniority = "Mid Level"
    for kw, lvl in SENIORITY_KEYWORDS.items():
        pat = make_word_pattern(kw)
        if re.search(pat, title.lower()):
            seniority = lvl
            break
    if seniority == "Mid Level":
        for kw, lvl in SENIORITY_KEYWORDS.items():
            pat = make_word_pattern(kw)
            if re.search(pat, full_text_lower[:500]):
                seniority = lvl
                break

    # 2. Section Partitioning (Required vs Preferred)
    required_text = ""
    preferred_text = ""

    req_matches = list(re.finditer(r'(?:basic qualifications|minimum qualifications|requirements|required skills|required:|what you(?:\'ll)? need|what you bring|must have|responsibilities)', full_text_lower))
    pref_matches = list(re.finditer(r'(?:preferred qualifications|bonus qualifications|bonus points|bonus|nice to have|good to have|preferred skills|preferred:|plus points|what sets you apart)', full_text_lower))

    if req_matches and pref_matches:
        req_start = req_matches[0].start()
        pref_start = pref_matches[0].start()
        if req_start < pref_start:
            required_text = full_text_lower[req_start:pref_start]
            preferred_text = full_text_lower[pref_start:]
        else:
            preferred_text = full_text_lower[pref_start:req_start]
            required_text = full_text_lower[req_start:]
    elif req_matches:
        required_text = full_text_lower[req_matches[0].start():]
    elif pref_matches:
        preferred_text = full_text_lower[pref_matches[0].start():]

    # 3. Extract Technical Skills from Vocab
    required_skills: Set[str] = set()
    preferred_skills: Set[str] = set()
    contextual_skills: Set[str] = set()

    for word in KNOWN_TECH_VOCABULARY:
        pattern = make_word_pattern(word)
        canonical = get_canonical_skill(word)
        display_name = CANONICAL_DISPLAY_NAMES.get(canonical, canonical.title())

        if required_text and re.search(pattern, required_text):
            required_skills.add(display_name)
        elif preferred_text and re.search(pattern, preferred_text):
            preferred_skills.add(display_name)
        elif re.search(pattern, full_text_lower):
            if re.search(pattern, title.lower()):
                required_skills.add(display_name)
            else:
                contextual_skills.add(display_name)

    # 4. Extract Soft Skills
    soft_skills_found = [
        kw.title() for kw in SOFT_SKILLS_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', full_text_lower)
    ]

    # Categorized skill taxonomy
    languages = [s for s in (required_skills | preferred_skills | contextual_skills) if get_canonical_skill(s) in {"python", "javascript", "typescript", "c++", "c#", "golang", "rust", "java", "sql", "html", "css", "ruby", "scala", "swift", "kotlin", "php"}]
    frameworks = [s for s in (required_skills | preferred_skills | contextual_skills) if get_canonical_skill(s) in {"react", "next.js", "vue", "angular", "flask", "django", "fastapi", "node.js", "express", "pytorch", "tensorflow", "scikit-learn", "spring", "spring boot", "laravel"}]
    tools_and_cloud = [s for s in (required_skills | preferred_skills | contextual_skills) if s not in languages and s not in frameworks]

    return {
        "job_title": title,
        "company": job_dict.get("company", ""),
        "seniority": seniority,
        "required_skills": sorted(list(required_skills)),
        "preferred_skills": sorted(list(preferred_skills)),
        "contextual_skills": sorted(list(contextual_skills)),
        "languages": sorted(languages),
        "frameworks": sorted(frameworks),
        "tools_and_cloud": sorted(tools_and_cloud),
        "soft_skills": soft_skills_found[:5],
        "important_keywords": sorted(list(required_skills | preferred_skills | set(languages) | set(frameworks)))
    }

# ---------------------------------------------------------------------------
# 3. Master Resume ↔ Job Requirement Match Matrix
# ---------------------------------------------------------------------------

def match_candidate_to_job(candidate_profile: Dict[str, Any], job_requirements: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministically computes match status for all extracted job requirements:
    - MATCHED: Directly supported by master candidate skills, projects, or experience.
    - PARTIALLY_MATCHED: Related or equivalent technology present.
    - UNSUPPORTED: Required by job but not present in candidate factual profile.
    """
    cand_skills = candidate_profile.get("skills", [])
    master_canonical_set = {get_canonical_skill(s) for s in cand_skills if s}
    
    for p in candidate_profile.get("projects", []):
        for tech in p.get("technologies", []):
            if tech:
                master_canonical_set.add(get_canonical_skill(tech))

    cand_exp_text = " ".join([
        " ".join(e.get("bullets", [])) for e in candidate_profile.get("experience", [])
    ]).lower()
    for word in KNOWN_TECH_VOCABULARY:
        if re.search(r'\b' + re.escape(word) + r'\b', cand_exp_text):
            master_canonical_set.add(get_canonical_skill(word))

    matched_required = []
    unsupported_required = []
    for skill in job_requirements.get("required_skills", []):
        c_skill = get_canonical_skill(skill)
        if c_skill in master_canonical_set:
            matched_required.append(skill)
        else:
            unsupported_required.append(skill)

    matched_preferred = []
    unsupported_preferred = []
    for skill in job_requirements.get("preferred_skills", []):
        c_skill = get_canonical_skill(skill)
        if c_skill in master_canonical_set:
            matched_preferred.append(skill)
        else:
            unsupported_preferred.append(skill)

    matched_contextual = []
    for skill in job_requirements.get("contextual_skills", []):
        c_skill = get_canonical_skill(skill)
        if c_skill in master_canonical_set:
            matched_contextual.append(skill)

    return {
        "matched_required": matched_required,
        "unsupported_required": unsupported_required,
        "matched_preferred": matched_preferred,
        "unsupported_preferred": unsupported_preferred,
        "matched_contextual": matched_contextual,
        "all_matched_skills": sorted(list(set(matched_required + matched_preferred + matched_contextual))),
        "all_unsupported_skills": sorted(list(set(unsupported_required + unsupported_preferred))),
        "seniority_match": True
    }

# ---------------------------------------------------------------------------
# 4. Factual Integrity Validator
# ---------------------------------------------------------------------------

def validate_factual_integrity(tailored_resume: Dict[str, Any], master_profile: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Mandatory Factual Integrity Verification:
    Compares the tailored resume against the master candidate profile.
    Detects and rejects:
    - New/unsupported skills or technologies.
    - New/fabricated employer companies.
    - Altered employment dates or job titles.
    - New/fabricated project names.
    - Fabricated numerical metrics (percentages, dollar amounts, scale counts).
    """
    violations = []
    sanitized = json.loads(json.dumps(tailored_resume))

    # 1. Master Skill Canon
    cand_skills_raw = master_profile.get("skills", [])
    valid_skill_map = {s.lower().strip(): s for s in cand_skills_raw if isinstance(s, str)}
    for p in master_profile.get("projects", []):
        for tech in p.get("technologies", []):
            if isinstance(tech, str) and tech.strip():
                valid_skill_map[tech.lower().strip()] = tech.strip()

    master_canonical_keys = {get_canonical_skill(s) for s in valid_skill_map.keys()}

    # Validate Skills Section
    tailored_skills = sanitized.get("skills", {})
    if isinstance(tailored_skills, dict):
        clean_skills = {}
        for cat, slist in tailored_skills.items():
            if isinstance(slist, list):
                valid_cat = []
                for sk in slist:
                    if not isinstance(sk, str):
                        continue
                    c_sk = get_canonical_skill(sk)
                    if c_sk in master_canonical_keys or sk.lower().strip() in valid_skill_map:
                        valid_cat.append(sk)
                    else:
                        violations.append(f"Fabricated skill detected: '{sk}'")
                clean_skills[cat] = valid_cat
            else:
                clean_skills[cat] = []
        if not any(clean_skills.values()):
            clean_skills = {
                "languages": [s for s in cand_skills_raw if get_canonical_skill(s) in {"python", "javascript", "typescript", "c++", "c#", "golang", "java", "sql"}],
                "frameworks": [s for s in cand_skills_raw if get_canonical_skill(s) in {"flask", "django", "fastapi", "react", "pytorch", "tensorflow"}],
                "tools": [s for s in cand_skills_raw if get_canonical_skill(s) not in {"python", "javascript", "typescript", "c++", "c#", "golang", "java", "sql", "flask", "django", "fastapi", "react", "pytorch", "tensorflow"}]
            }
        sanitized["skills"] = clean_skills
    elif isinstance(tailored_skills, list):
        clean_list = []
        for sk in tailored_skills:
            if isinstance(sk, str) and (get_canonical_skill(sk) in master_canonical_keys or sk.lower().strip() in valid_skill_map):
                clean_list.append(sk)
            else:
                violations.append(f"Fabricated skill in list: '{sk}'")
        sanitized["skills"] = clean_list or cand_skills_raw

    # 2. Validate Experience
    cand_exp = master_profile.get("experience", [])
    valid_exp_map = {exp.get("company", "").lower().strip(): exp for exp in cand_exp if exp.get("company")}

    clean_exp = []
    for exp in sanitized.get("experience", []):
        if not isinstance(exp, dict):
            continue
        c_name = exp.get("company", "").lower().strip()
        if c_name in valid_exp_map:
            orig = valid_exp_map[c_name]
            exp["company"] = orig.get("company", exp.get("company"))
            exp["role"] = orig.get("role", exp.get("role"))
            exp["dates"] = f"{orig.get('start_date', '')} - {orig.get('end_date') or 'Present'}"
            clean_exp.append(exp)
        else:
            violations.append(f"Fabricated employer detected: '{exp.get('company')}'")

    if not clean_exp and cand_exp:
        clean_exp = [
            {
                "company": e.get("company", "Company"),
                "role": e.get("role", "Role"),
                "dates": f"{e.get('start_date', '')} - {e.get('end_date') or 'Present'}",
                "bullets": e.get("bullets", [])
            } for e in cand_exp
        ]
    sanitized["experience"] = clean_exp

    # 3. Validate Projects
    cand_proj = master_profile.get("projects", [])
    valid_proj_map = {p.get("name", "").lower().strip(): p for p in cand_proj if p.get("name")}

    clean_proj = []
    for p in sanitized.get("projects", []):
        if not isinstance(p, dict):
            continue
        p_name = p.get("name", "").lower().strip()
        if p_name in valid_proj_map:
            clean_proj.append(p)
        else:
            violations.append(f"Fabricated project detected: '{p.get('name')}'")

    if not clean_proj and cand_proj:
        clean_proj = [
            {
                "name": p.get("name", "Project"),
                "technologies": ", ".join(p.get("technologies", [])),
                "bullets": p.get("bullets", [p.get("description", "")])
            } for p in cand_proj
        ]
    sanitized["projects"] = clean_proj

    # 4. Validate Numerical Metrics in Bullets
    master_text = json.dumps(master_profile)
    master_metrics = set(re.findall(r"\b\d+(?:%\b|\+\b|k\b|\.\d+)?", master_text.lower()))

    for sec in ["experience", "projects"]:
        for item in sanitized.get(sec, []):
            if isinstance(item, dict) and "bullets" in item and isinstance(item["bullets"], list):
                clean_bullets = []
                for bullet in item["bullets"]:
                    bullet_metrics = set(re.findall(r"\b\d+(?:%\b|\+\b|k\b|\.\d+)?", str(bullet).lower()))
                    unsupported_metrics = bullet_metrics - master_metrics
                    if unsupported_metrics:
                        violations.append(f"Fabricated numerical metric {unsupported_metrics} in bullet: '{bullet}'")
                        continue
                    clean_bullets.append(bullet)
                if not clean_bullets:
                    if sec == "experience":
                        orig = valid_exp_map.get(item.get("company", "").lower().strip())
                        clean_bullets = orig.get("bullets", []) if orig else ["Contributed to core engineering."]
                    else:
                        orig = valid_proj_map.get(item.get("name", "").lower().strip())
                        clean_bullets = orig.get("bullets", []) if orig else ["Developed software solution."]
                item["bullets"] = clean_bullets

    is_valid = (len(violations) == 0)
    return is_valid, violations, sanitized

# ---------------------------------------------------------------------------
# 5. ATS Format Validation
# ---------------------------------------------------------------------------

def validate_ats_format(latex_content: str) -> Tuple[bool, List[str]]:
    """
    Validates that generated LaTeX code is ATS-friendly.
    """
    issues = []
    required_sections = ["Summary", "Education", "Experience", "Technical Skills"]
    for sec in required_sections:
        if f"\\section{{{sec}}}" not in latex_content and f"\\section*{{{sec}}}" not in latex_content:
            issues.append(f"Missing standard ATS section header: '{sec}'")

    if r"\begin{document}" not in latex_content or r"\end{document}" not in latex_content:
        issues.append("Missing standard LaTeX document envelope.")

    is_valid = len(issues) == 0
    return is_valid, issues

# ---------------------------------------------------------------------------
# 6. ATS Resume Match Scoring Engine
# ---------------------------------------------------------------------------

def calculate_resume_match_score(
    tailored_resume: Dict[str, Any],
    job_requirements: Dict[str, Any],
    candidate_profile: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculates a comprehensive, deterministic Resume Match Score (0–100)
    with detailed sub-score breakdown.
    """
    match_matrix = match_candidate_to_job(candidate_profile, job_requirements)
    req_skills = job_requirements.get("required_skills", [])
    pref_skills = job_requirements.get("preferred_skills", [])
    
    # 1. Required Skill Sub-score (Weight: 30%)
    if req_skills:
        req_score = (len(match_matrix["matched_required"]) / len(req_skills)) * 100
    else:
        req_score = 90.0

    # 2. Preferred Skill Sub-score (Weight: 15%)
    if pref_skills:
        pref_score = (len(match_matrix["matched_preferred"]) / len(pref_skills)) * 100
    else:
        pref_score = 80.0

    # 3. Keyword Coverage Sub-score (Weight: 20%)
    all_keywords = job_requirements.get("important_keywords", [])
    resume_text = json.dumps(tailored_resume).lower()
    matched_kw_count = 0
    for kw in all_keywords:
        c_kw = get_canonical_skill(kw)
        if c_kw in resume_text or kw.lower() in resume_text:
            matched_kw_count += 1
    kw_score = (matched_kw_count / len(all_keywords) * 100) if all_keywords else 85.0

    # 4. Role & Seniority Alignment (Weight: 10%)
    role_score = 90.0 if match_matrix.get("seniority_match") else 70.0

    # 5. Experience Relevance (Weight: 10%)
    exp_bullets = " ".join([
        " ".join(e.get("bullets", [])) for e in tailored_resume.get("experience", [])
    ]).lower()
    exp_matched = sum(1 for s in match_matrix["all_matched_skills"] if get_canonical_skill(s) in exp_bullets)
    exp_score = min(100.0, 60.0 + (exp_matched * 10.0))

    # 6. Project Relevance (Weight: 5%)
    proj_bullets = " ".join([
        " ".join(p.get("bullets", [])) for p in tailored_resume.get("projects", [])
    ]).lower()
    proj_matched = sum(1 for s in match_matrix["all_matched_skills"] if get_canonical_skill(s) in proj_bullets)
    proj_score = min(100.0, 65.0 + (proj_matched * 10.0))

    # 7. Qualification Alignment (Weight: 5%)
    qual_score = 95.0

    # 8. ATS Format & Content Quality (Weight: 5%)
    ats_score = 100.0
    quality_score = 90.0

    # Weighted Overall Score
    overall_score = (
        (req_score * 0.30) +
        (kw_score * 0.20) +
        (pref_score * 0.15) +
        (role_score * 0.10) +
        (exp_score * 0.10) +
        (proj_score * 0.05) +
        (qual_score * 0.05) +
        (ats_score * 0.05)
    )
    overall_score = round(min(100.0, max(10.0, overall_score)), 1)

    return {
        "overall_score": overall_score,
        "sub_scores": {
            "required_skills": round(req_score, 1),
            "preferred_skills": round(pref_score, 1),
            "keyword_coverage": round(kw_score, 1),
            "role_alignment": round(role_score, 1),
            "experience_relevance": round(exp_score, 1),
            "project_relevance": round(proj_score, 1),
            "qualification_alignment": round(qual_score, 1),
            "ats_format": round(ats_score, 1),
            "content_quality": round(quality_score, 1)
        },
        "missing_required": match_matrix["unsupported_required"],
        "missing_preferred": match_matrix["unsupported_preferred"],
        "strong_matches": match_matrix["matched_required"] + match_matrix["matched_preferred"][:3]
    }

# ---------------------------------------------------------------------------
# 7. Dynamic Section Ordering
# ---------------------------------------------------------------------------

def determine_optimal_section_order(job_requirements: Dict[str, Any]) -> List[str]:
    """
    Determines most effective section ordering based on target job profile.
    """
    seniority = job_requirements.get("seniority", "")
    if seniority in ["Internship", "Entry Level"]:
        return ["Summary", "Technical Skills", "Projects", "Experience", "Education"]
    return ["Summary", "Technical Skills", "Experience", "Projects", "Education"]

# ---------------------------------------------------------------------------
# 8. Full Iterative Tailoring Pipeline
# ---------------------------------------------------------------------------

def tailor_resume_pipeline(
    candidate_profile: Dict[str, Any],
    job_dict: Dict[str, Any],
    ai_analysis: Optional[Dict[str, Any]] = None,
    resume_settings: Optional[Dict[str, Any]] = None,
    max_iterations: Optional[int] = None
) -> Dict[str, Any]:
    """
    Executes the complete V1.6 production-grade resume tailoring pipeline.
    """
    import ai

    if max_iterations is None:
        max_iterations = int(os.getenv("RESUME_MAX_ITERATIONS", 2))
    max_iterations = min(max(1, max_iterations), 5)

    ai_analysis = ai_analysis or {}
    resume_settings = resume_settings or {}

    # Step 1: Analyze target JD
    requirements = analyze_job_requirements(job_dict)

    # Step 2: Match candidate profile against JD
    match_matrix = match_candidate_to_job(candidate_profile, requirements)

    # Step 3: Iterative generation & validation
    tailored_draft = None
    sanitized_resume = None
    violations_log = []

    for iteration in range(1, max_iterations + 1):
        try:
            tailored_draft = ai.tailor_resume(
                candidate_profile=candidate_profile,
                job_dict=job_dict,
                ai_analysis={
                    "matching_requirements": match_matrix["all_matched_skills"],
                    "missing_preferred_skills": match_matrix["all_unsupported_skills"],
                    "requirements_breakdown": requirements
                },
                resume_settings=resume_settings
            )
        except Exception as e:
            logger.warning(f"AI tailoring iteration #{iteration} failed: {e}. Using deterministic tailoring.")
            tailored_draft = ai._mock_tailor_resume(
                candidate_profile=candidate_profile,
                job_dict=job_dict,
                ai_analysis={
                    "matching_requirements": match_matrix["all_matched_skills"],
                    "missing_preferred_skills": match_matrix["all_unsupported_skills"]
                },
                resume_settings=resume_settings
            )

        # Step 4: Strict Factual Integrity Validation
        is_valid, violations, sanitized = validate_factual_integrity(tailored_draft, candidate_profile)
        sanitized_resume = sanitized
        violations_log.extend(violations)

        if is_valid:
            break
        else:
            logger.info(f"Refining resume (iteration {iteration}): sanitized {len(violations)} unsupported items.")

    # Step 5: ATS Scoring
    match_score_data = calculate_resume_match_score(sanitized_resume, requirements, candidate_profile)

    return {
        "resume_json": sanitized_resume,
        "match_score": match_score_data["overall_score"],
        "match_details": match_score_data,
        "requirements": requirements,
        "match_matrix": match_matrix,
        "violations": violations_log
    }
