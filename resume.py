import os
import re
import logging
import subprocess
import shutil
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

PDFLATEX_PATH = os.getenv("PDFLATEX_PATH", "pdflatex")

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts raw text content from an uploaded PDF resume."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"CV file not found: {pdf_path}")
        
    extracted_text = ""
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
    except Exception as e:
        logger.error(f"Error reading PDF with pypdf: {e}")
        raise RuntimeError(f"Could not extract text from PDF: {e}")
        
    if not extracted_text.strip():
        raise ValueError("Extracted text from PDF is empty. Ensure the file is not a scanned image.")
        
    return extracted_text.strip()

def latex_escape(text: Any) -> str:
    r"""
    Escapes all LaTeX special characters in user/AI-provided text.
    Handles: &, %, $, #, _, {, }, \, ^, ~
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # Replace backslash first to prevent escaping replacement backslashes
    text = text.replace('\\', r'\textbackslash{}')
    
    # Escape standard special characters
    special_chars = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '^': r'\textasciicircum{}',
        '~': r'\textasciitilde{}',
    }
    
    for char, replacement in special_chars.items():
        text = text.replace(char, replacement)
        
    return text

def sanitize_filename(name: str) -> str:
    """Sanitizes company/job title string for safe filesystem paths."""
    clean = re.sub(r'[\s/\\:\*\?"<>\|]+', '_', name)
    return clean.strip('_')[:60]

def render_latex(resume_json: Dict[str, Any], template_path: str = "latex/resume_template.tex") -> str:
    """Populates the LaTeX template using escaped fields from structured Resume JSON."""
    header = resume_json.get("header", {})
    name = latex_escape(header.get("name", "Candidate Name"))
    email = latex_escape(header.get("email", ""))
    phone = latex_escape(header.get("phone", ""))
    
    links = header.get("links", {})
    linkedin = latex_escape(links.get("linkedin", "")) if isinstance(links, dict) else ""
    github = latex_escape(links.get("github", "")) if isinstance(links, dict) else ""
    
    summary = latex_escape(resume_json.get("summary", ""))
    
    # Education block
    education_blocks = []
    for ed in resume_json.get("education", []):
        degree = latex_escape(ed.get("degree", ""))
        inst = latex_escape(ed.get("institution", ""))
        year = latex_escape(ed.get("year", ""))
        details = latex_escape(ed.get("details", ""))
        detail_str = f" ({details})" if details else ""
        education_blocks.append(
            f"\\resumeSubheading{{{inst}}}{{{year}}}{{{degree}{detail_str}}}{{}}"
        )
    education_tex = "\n".join(education_blocks)
    
    # Experience block
    experience_blocks = []
    for exp in resume_json.get("experience", []):
        comp = latex_escape(exp.get("company", ""))
        role = latex_escape(exp.get("role", ""))
        dates = latex_escape(exp.get("dates", ""))
        
        bullets = exp.get("bullets", [])
        bullet_items = "\n".join([f"  \\item {latex_escape(b)}" for b in bullets if b])
        
        block = f"""\\resumeSubheading{{{comp}}}{{{dates}}}{{{role}}}{{}}
\\resumeItemListStart
{bullet_items}
\\resumeItemListEnd"""
        experience_blocks.append(block)
    experience_tex = "\n\n".join(experience_blocks)
    
    # Projects block
    project_blocks = []
    for proj in resume_json.get("projects", []):
        p_name = latex_escape(proj.get("name", ""))
        p_tech = latex_escape(proj.get("technologies", ""))
        tech_str = f" $|$ \\textit{{{p_tech}}}" if p_tech else ""
        
        bullets = proj.get("bullets", [])
        bullet_items = "\n".join([f"  \\item {latex_escape(b)}" for b in bullets if b])
        
        block = f"""\\resumeProjectHeading{{\\textbf{{{p_name}}}{tech_str}}}{{}}
\\resumeItemListStart
{bullet_items}
\\resumeItemListEnd"""
        project_blocks.append(block)
    project_tex = "\n\n".join(project_blocks)
    
    # Skills block
    skills = resume_json.get("skills", {})
    if isinstance(skills, dict):
        languages = latex_escape(", ".join(skills.get("languages", [])))
        frameworks = latex_escape(", ".join(skills.get("frameworks", [])))
        tools = latex_escape(", ".join(skills.get("tools", [])))
    else:
        languages = latex_escape(", ".join(skills)) if isinstance(skills, list) else ""
        frameworks = ""
        tools = ""
        
    skills_tex = f"""\\textbf{{Languages:}} {{{languages}}} \\\\
\\textbf{{Frameworks \\& Libraries:}} {{{frameworks}}} \\\\
\\textbf{{Tools \\& Technologies:}} {{{tools}}}"""

    # Load template
    if not os.path.exists(template_path):
        latex_content = _generate_default_latex_template()
    else:
        with open(template_path, "r", encoding="utf-8") as f:
            latex_content = f.read()

    # Placeholders replacement
    replacements = {
        "{{NAME}}": name,
        "{{EMAIL}}": email,
        "{{PHONE}}": phone,
        "{{LINKEDIN}}": linkedin,
        "{{GITHUB}}": github,
        "{{SUMMARY}}": summary,
        "{{EDUCATION_SECTION}}": education_tex,
        "{{EXPERIENCE_SECTION}}": experience_tex,
        "{{PROJECTS_SECTION}}": project_tex,
        "{{SKILLS_SECTION}}": skills_tex
    }
    
    for key, val in replacements.items():
        latex_content = latex_content.replace(key, val)
        
    return latex_content

def _generate_default_latex_template() -> str:
    """Returns standard ATS-optimized single page LaTeX template."""
    return r"""\documentclass[letterpaper,11pt]{article}

\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}

\pagestyle{fancy}
\fancyhf{} 
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-.5in}
\addtolength{\textheight}{1.0in}

\urlstyle{same}

\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

\titleformat{\section}{
  \vspace{-4pt}\scshape\raggedright\large
}{}{0em}{}[\color{black}\vline height 0.8pt\vspace{-5pt}]

\newcommand{\resumeItem}[1]{
  \item\small{
    {#1 \vspace{-2pt}}
  }
}

\newcommand{\resumeSubheading}[4]{
  \vspace{-2pt}\item
    \begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}
      \textbf{#1} & #2 \\
      \textit{\small#3} & \textit{\small #4} \\
    \end{tabular*}\vspace{-7pt}
}

\newcommand{\resumeProjectHeading}[2]{
    \item
    \begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}
      \small#1 & #2 \\
    \end{tabular*}\vspace{-7pt}
}

\newcommand{\resumeItemListStart}{\begin{itemize}[leftmargin=0.15in, label={--}]}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}

\begin{document}

\begin{center}
    \textbf{\Huge \scshape {{NAME}}} \\ \vspace{1pt}
    \small {{PHONE}} $|$ \href{mailto:{{EMAIL}}}{{EMAIL}} $|$ {{LINKEDIN}} $|$ {{GITHUB}}
\end{center}

\section{Summary}
\small{{{SUMMARY}}}

\section{Education}
\begin{itemize}[leftmargin=0.15in, label={}]
{{EDUCATION_SECTION}}
\end{itemize}

\section{Experience}
\begin{itemize}[leftmargin=0.15in, label={}]
{{EXPERIENCE_SECTION}}
\end{itemize}

\section{Projects}
\begin{itemize}[leftmargin=0.15in, label={}]
{{PROJECTS_SECTION}}
\end{itemize}

\section{Technical Skills}
\begin{itemize}[leftmargin=0.15in, label={}]
  \item \small{
    {{SKILLS_SECTION}}
  }
\end{itemize}

\end{document}
"""

def create_latex_template_file(template_path: str = "latex/resume_template.tex") -> None:
    """Ensures default resume_template.tex exists on disk."""
    dir_name = os.path.dirname(template_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    if not os.path.exists(template_path):
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(_generate_default_latex_template())

def compile_pdf(tex_path: str, output_dir: str = "generated/resumes") -> Tuple[bool, Optional[str], str]:
    """
    Compiles a .tex file into a PDF using pdflatex.
    Resolves pdflatex from:
      1. os.getenv("PDFLATEX_PATH")
      2. shutil.which("pdflatex")
    Cleans up auxiliary files (.aux, .log, .out) upon compilation.
    Returns tuple: (success: bool, pdf_path: str or None, error_log: str).
    Never crashes the pipeline on pdflatex error.
    """
    os.makedirs(output_dir, exist_ok=True)
    tex_path = os.path.abspath(tex_path)
    tex_dir = os.path.dirname(tex_path)
    base_name = os.path.splitext(os.path.basename(tex_path))[0]
    expected_pdf = os.path.join(output_dir, f"{base_name}.pdf")

    # Locate pdflatex command dynamically
    env_path = os.getenv("PDFLATEX_PATH")
    cmd = None
    if env_path and os.path.exists(env_path):
        cmd = env_path
    elif env_path and shutil.which(env_path):
        cmd = shutil.which(env_path)
    else:
        cmd = shutil.which("pdflatex")

    if not cmd:
        err_msg = "pdflatex command not found on system PATH. .tex generated successfully."
        logger.warning(err_msg)
        return False, None, err_msg

    try:
        # Run pdflatex with safe security arguments and non-interactive mode
        process = subprocess.run(
            [
                cmd,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-no-shell-escape",
                f"-output-directory={os.path.abspath(output_dir)}",
                tex_path
            ],
            cwd=tex_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            text=True
        )
        
        # Clean up temporary LaTeX auxiliary files
        for ext in [".aux", ".log", ".out"]:
            aux_file = os.path.join(output_dir, f"{base_name}{ext}")
            if os.path.exists(aux_file):
                try:
                    os.remove(aux_file)
                except OSError:
                    pass

        if process.returncode == 0 and os.path.exists(expected_pdf) and os.path.getsize(expected_pdf) > 0:
            return True, expected_pdf, "PDF compiled successfully."
        else:
            err_log = process.stdout or process.stderr or "pdflatex exit code non-zero."
            logger.warning(f"pdflatex compilation non-zero for {tex_path}: {err_log[:300]}")
            return False, None, err_log
    except Exception as e:
        logger.error(f"Error executing pdflatex: {e}")
        return False, None, str(e)
