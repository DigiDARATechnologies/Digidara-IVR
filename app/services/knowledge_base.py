"""
DigiDARA Technologies — Complete Knowledge Base for RAG
Source: knowledge.txt (FINAL v2, compiled 2026-06-19)
Covers: Company, Products, Services, Courses, Internships, Career Support,
        Founder, Testimonials, FAQs, Contact, Demo Booking
"""

from typing import Dict, List, TypedDict


class KBDocument(TypedDict):
    id: str
    text: str
    metadata: Dict[str, str]


# ─────────────────────────────────────────────────────────────────────────────
# COMPANY collection
# ─────────────────────────────────────────────────────────────────────────────
COMPANY_DOCS: List[KBDocument] = [
    {
        "id": "company_overview",
        "text": (
            "DigiDARA Technologies Private Limited is an ISO-certified AI training and consulting company "
            "headquartered in Trichy, Tamil Nadu, India. Founded in 2023 by Senthil Rajamarthandan, a 28+ year IT veteran from "
            "HCL Technologies and Cognizant. DigiDARA democratizes AI education and empowers individuals and "
            "businesses to harness Artificial Intelligence. Has trained 5000+ students, delivered 100+ live projects, "
            "partnered with 50+ colleges and industries, and built 6+ AI agents. "
            "Rating: 4.9/5 from verified reviews."
        ),
        "metadata": {"collection": "company", "topic": "overview"},
    },
    {
        "id": "company_mission_vision",
        "text": (
            "Mission: To close the global AI skills gap by delivering practical, project-based AI education "
            "and enterprise consulting that make learners and businesses future-ready. "
            "Vision: To make Trichy a global hub for AI innovation and empower 1 million AI-ready learners "
            "and leaders by 2030. "
            "Three Pillars: Training, Implementation, Transformation. "
            "Core Divisions: DigiDARA Academy (AI Training and Internships), "
            "DigiDARA Consulting (AI Strategy and Automation Solutions), "
            "DigiDARA R&D (AI Agent Development and Innovation Lab)."
        ),
        "metadata": {"collection": "company", "topic": "mission_vision"},
    },
    {
        "id": "company_certifications",
        "text": (
            "DigiDARA Technologies is ISO-certified: ISO 9001:2015 (Quality Management), "
            "ISO 27001:2013 (Information Security), ISO 20000-1:2018 (IT Service Management). "
            "ISO-aligned certificates are issued for all training programs and internships."
        ),
        "metadata": {"collection": "company", "topic": "certifications"},
    },
    {
        "id": "company_unique",
        "text": (
            "What makes DigiDARA unique: AI for Every Generation — courses for students, educators, and professionals. "
            "Real-World Implementation — every module includes a live project or AI agent prototype. "
            "Industry Integration — programs align with corporate AI initiatives and placement goals. "
            "Expert Mentorship — delivered by AI architects and data scientists with 10+ years of experience. "
            "Ethical AI Focus — responsible, secure, transparent AI usage. "
            "Industries served: Engineering Colleges, SME Businesses, Retail & E-Commerce, Healthcare, "
            "Digital Agencies, Finance & Consulting."
        ),
        "metadata": {"collection": "company", "topic": "unique_value"},
    },
    {
        "id": "company_impact",
        "text": (
            "DigiDARA impact numbers: 5000+ students trained, 100+ live projects delivered, "
            "50+ college and industry partners, 6+ AI agents built. "
            "Key stats: 6+ proprietary AI products, 4 AI services, 15+ business clients, "
            "15+ college partners, 4.9/5 rating from 10+ verified reviews."
        ),
        "metadata": {"collection": "company", "topic": "impact"},
    },
    # FAQs mapped to company
    {"id": "faq_what_is_digidara", "text": "Q: What is DigiDARA Technologies?\nA: DigiDARA Technologies is an ISO-certified AI education and consulting company based in Trichy, Tamil Nadu. We offer hands-on courses in Data Science, Generative AI, and Agentic AI, while helping businesses adopt AI solutions. Learn more at https://www.digidaratechnologies.com/about", "metadata": {"collection": "company", "keywords": "about company who overview"}},
    {"id": "faq_mission_vision", "text": "Q: What is DigiDARA's mission and vision?\nA: Our mission is to close the global AI skills gap through practical, project-based education and consulting. Our vision is to make Trichy a global AI hub and empower 1 million AI-ready learners and leaders by 2030.", "metadata": {"collection": "company", "keywords": "mission vision goal purpose"}},
    {"id": "faq_different", "text": "Q: What makes DigiDARA different from other institutes?\nA: Unlike traditional training centres, DigiDARA combines Generative AI and Agentic AI Frameworks — LangChain, LangGraph, RAG — with real-world projects, ISO certification, and career support to deliver measurable results.", "metadata": {"collection": "company", "keywords": "different unique why choose"}},
    {"id": "faq_iso_certified", "text": "Q: Is DigiDARA ISO certified?\nA: Yes. ISO 9001:2015 for Quality Management, ISO 27001:2013 for Information Security, and ISO 20000-1:2018 for IT Service Management.", "metadata": {"collection": "company", "keywords": "iso certified quality"}},
    {"id": "faq_best_ai_trichy", "text": "Q: What is the best AI company in Trichy?\nA: DigiDARA Technologies is recognized as the best AI company in Trichy (Tiruchirappalli), providing top-tier AI services, custom development, and professional training in Tamil Nadu.", "metadata": {"collection": "company", "keywords": "best ai trichy tiruchirappalli"}},
    {"id": "faq_ai_training_trichy", "text": "Q: Do you provide AI training in Trichy?\nA: Yes, DigiDARA provides industry-leading AI training in Trichy, Tamil Nadu. Programs cover Machine Learning, Generative AI, and Data Science with practical, real-world project experience.", "metadata": {"collection": "company", "keywords": "ai training trichy tamil nadu"}},
]

# ─────────────────────────────────────────────────────────────────────────────
# FOUNDER collection
# ─────────────────────────────────────────────────────────────────────────────
FOUNDER_DOCS: List[KBDocument] = [
    {
        "id": "founder_profile",
        "text": (
            "Founder: Senthil Rajamarthandan, Founder and Managing Director of DigiDARA Technologies. "
            "Experience: 28+ years in IT at HCL Technologies and Cognizant. "
            "Expertise: Generative AI and Agentic AI Frameworks (LangChain, LangGraph, RAG), "
            "AI-Driven Business Transformation for MSMEs and Enterprises, Cloud Computing and Automation, "
            "AI Strategy and Responsible AI Governance, AI Training and Mentorship. "
            "Mission: Help one million learners and business leaders achieve 10x growth through AI. "
            "Highlights: Mentored 5000+ students, established DigiDARA as ISO-certified AI brand, "
            "built AI Agents: EduMate, MindMate, CareerMate, CanteenMate, InfoMate. "
            "LinkedIn: https://www.linkedin.com/company/104865843/ "
            "Portfolio: https://senthilrajamarthandan.com/"
        ),
        "metadata": {"collection": "founder", "topic": "profile"},
    },
    {"id": "faq_founder", "text": "Q: Who is the founder of DigiDARA Technologies?\nA: Mr. Senthil Rajamarthandan, Founder and MD, with 27+ years of IT experience at HCL and Cognizant. He is an AI Transformation Strategist specializing in Generative AI, Agentic AI, and enterprise consulting.", "metadata": {"collection": "founder", "keywords": "founder senthil who started"}},
    {"id": "faq_founder_motivation", "text": "Q: What motivated the founder to start DigiDARA?\nA: He wanted to bridge the gap between academic learning and industry readiness by making AI education accessible and practical for all learners in India.", "metadata": {"collection": "founder", "keywords": "motivation why started digidara"}},
    {"id": "faq_ai_agents_built", "text": "Q: What AI agents has DigiDARA built?\nA: EduMate for student information, CareerMate for HR and resume assistance, InfoMate for knowledge retrieval, MindMate for productivity and wellness, CanteenMate for food services, and custom business chatbots with lead-tracking automation.", "metadata": {"collection": "founder", "keywords": "ai agents edumate careermate built"}},
]

# ─────────────────────────────────────────────────────────────────────────────
# COURSES collection
# ─────────────────────────────────────────────────────────────────────────────
COURSES_DOCS: List[KBDocument] = [
    {
        "id": "courses_overview",
        "text": (
            "DigiDARA offers 6 practical, portfolio-ready AI training programs. All courses: "
            "Duration 3 months each. Modes: Online, Offline (Trichy), Hybrid. "
            "Includes: hands-on labs, mini-projects, capstone project, ISO-aligned DigiDARA certificate, "
            "lifetime access to recordings, placement support. "
            "Programs: Data Science and Data Analytics Mastery, Artificial Intelligence and Machine Learning, "
            "Generative AI and Agentic AI Frameworks, AI in Digital Marketing, "
            "Python Full Stack Development, AI for Managers and Business Leaders. "
            "View all: https://www.digidaratechnologies.com/courses"
        ),
        "metadata": {"collection": "courses", "topic": "overview"},
    },
    {
        "id": "course_data_science",
        "text": (
            "Course: Data Science and Data Analytics Mastery. Duration: 3 Months. Mode: Online/Offline/Hybrid. "
            "Topics: data wrangling, cleaning, visualization, EDA using Pandas and NumPy, statistical analysis, "
            "hypothesis testing, Power BI, Tableau, business analytics projects. "
            "Tools: Python, Pandas, NumPy, Matplotlib, Seaborn, Power BI, Tableau. "
            "Outcome: Build interactive dashboards and make data-driven business decisions. "
            "URL: https://www.digidaratechnologies.com/courses/data-science"
        ),
        "metadata": {"collection": "courses", "topic": "data_science"},
    },
    {
        "id": "course_ai_ml",
        "text": (
            "Course: Artificial Intelligence and Machine Learning Professional Program. Duration: 3 Months. Mode: Online/Offline/Hybrid. "
            "Topics: AI and ML fundamentals, Supervised and Unsupervised Learning, Deep Learning and Neural Networks, "
            "model training, testing and optimization, real-world automation and prediction. "
            "Tools: TensorFlow, Keras, Scikit-learn, Jupyter Notebook. "
            "Outcome: Build, train, and deploy intelligent ML models for multiple industries. "
            "URL: https://www.digidaratechnologies.com/courses/ai-ml"
        ),
        "metadata": {"collection": "courses", "topic": "ai_ml"},
    },
    {
        "id": "course_genai_agentic",
        "text": (
            "Course: Generative AI and Agentic AI Frameworks Certification. Duration: 3 Months. Mode: Online/Offline/Hybrid. "
            "Topics: Generative AI and Agentic AI fundamentals, Prompt Engineering (basic to advanced), "
            "RAG pipelines with ChromaDB and FAISS, LangChain and LangGraph agent workflows, "
            "memory, planning and multi-tool orchestration, Streamlit UI and FastAPI backend deployment. "
            "Tools: GPT Models, Gemini, LangChain, LangGraph, ChromaDB, FAISS, Streamlit, FastAPI. "
            "Outcome: Build and deploy intelligent AI Agents — EduMate, CareerMate, InfoMate, CanteenMate. "
            "URL: https://www.digidaratechnologies.com/courses/genai"
        ),
        "metadata": {"collection": "courses", "topic": "genai_agentic"},
    },
    {
        "id": "course_digital_marketing",
        "text": (
            "Course: AI in Digital Marketing. Duration: 3 Months. Mode: Online/Offline/Hybrid. "
            "Topics: AI-driven content creation, campaign management, audience segmentation, AI ad targeting, "
            "social media and website analytics, Generative AI for ad copy, video and posts, "
            "WhatsApp and email marketing automation. "
            "Tools: ChatGPT, Jasper, Canva Magic Write, HubSpot AI, Google Ads AI. "
            "Outcome: Create and optimize high-performing digital campaigns with measurable ROI. "
            "URL: https://www.digidaratechnologies.com/courses/ai-digital-marketing"
        ),
        "metadata": {"collection": "courses", "topic": "digital_marketing"},
    },
    {
        "id": "course_python_fullstack",
        "text": (
            "Course: Python Full Stack Development Program. Duration: 3 Months. Mode: Online/Offline/Hybrid. "
            "Topics: Frontend: HTML, CSS, JavaScript, React. Backend: Python with Flask and Django. "
            "Database: SQL and NoSQL. API integration, authentication, cloud deployment, CI/CD pipeline. "
            "Tools: Python, React, Flask, Django, MySQL, MongoDB, AWS. "
            "Outcome: Build and professionally deploy full-stack applications. "
            "URL: https://www.digidaratechnologies.com/courses/python-fullstack"
        ),
        "metadata": {"collection": "courses", "topic": "python_fullstack"},
    },
    {
        "id": "course_ai_managers",
        "text": (
            "Course: AI for Managers and Business Leaders. Duration: 3 Months. Mode: Online/Offline/Hybrid. "
            "Topics: AI fundamentals for decision-making, identifying AI opportunities in business, "
            "data governance and ethical AI, designing AI transformation strategies, global AI case studies. "
            "Outcome: Lead AI-driven organizational change by aligning strategy, technology, and people. "
            "URL: https://digidaratechnologies.com/courses/ai-business-leaders"
        ),
        "metadata": {"collection": "courses", "topic": "ai_managers"},
    },
    # Course FAQs
    {"id": "faq_which_courses", "text": "Q: Which courses does DigiDARA offer?\nA: We offer 6 programs: Data Science and Analytics (3M), AI and ML (3M), Generative and Agentic AI (3M), AI in Digital Marketing (3M), Python Full Stack (3M), and AI for Managers (3M). View all at https://www.digidaratechnologies.com/courses", "metadata": {"collection": "courses", "keywords": "courses list programs what training"}},
    {"id": "faq_courses_beginners", "text": "Q: Are DigiDARA courses suitable for beginners?\nA: Yes. All courses start from foundational concepts and progress to advanced hands-on projects, making them ideal for beginners, working professionals, and upskillers alike.", "metadata": {"collection": "courses", "keywords": "beginner suitable prior experience"}},
    {"id": "faq_courses_certificate", "text": "Q: Do the courses include projects and a certificate?\nA: Yes. Every program includes real-world mini-projects and a capstone project, plus an ISO-aligned DigiDARA certificate recognized by educational and industry partners.", "metadata": {"collection": "courses", "keywords": "certificate project capstone included"}},
    {"id": "faq_courses_online_offline", "text": "Q: Are classes available online and offline?\nA: Yes. We offer Online, Offline at our Trichy center, and Hybrid learning modes with live and recorded sessions for maximum flexibility.", "metadata": {"collection": "courses", "keywords": "online offline hybrid mode"}},
    {"id": "faq_group_corporate", "text": "Q: Does DigiDARA offer group or corporate training?\nA: Yes. Group discounts are available for 3 or more participants, and custom corporate AI training programs are offered. Contact support@digidaratechnologies.com or call +91-95004-06945.", "metadata": {"collection": "courses", "keywords": "group corporate training discount"}},
]

# ─────────────────────────────────────────────────────────────────────────────
# INTERNSHIPS collection
# ─────────────────────────────────────────────────────────────────────────────
INTERNSHIPS_DOCS: List[KBDocument] = [
    {
        "id": "internship_overview",
        "text": (
            "DigiDARA Internship Programs give students real-world AI, Data Science, and Full Stack experience. "
            "Framework: Learn → Build → Showcase. "
            "Duration: 15 Days to 1 Month. Modes: Online, Offline, Hybrid. "
            "Includes: 2 mini-projects + 1 capstone project, 1:1 mentorship, weekly review sessions, "
            "ISO-aligned internship certificate, Letter of Recommendation (LOR) for top performers, "
            "GitHub portfolio guidance, LinkedIn profile optimization, mock interviews and technical drills, "
            "Demo Day: present capstone to mentors and industry reviewers. "
            "Apply: https://www.digidaratechnologies.com/internships | "
            "WhatsApp: https://wa.me/919500406945?text=Hi%20DigiDARA%2C%20I%27d%20like%20to%20apply%20for%20an%20internship"
        ),
        "metadata": {"collection": "internships", "topic": "overview"},
    },
    {
        "id": "internship_tracks",
        "text": (
            "DigiDARA internship tracks: "
            "1. Data Science and Data Analytics Internship — 1 Month. "
            "2. Artificial Intelligence and Machine Learning Internship — 1 Month. "
            "3. Generative AI and Agentic AI Internship — 1 Month. "
            "4. Python Full Stack Development Internship — 15 Days to 1 Month. "
            "5. AI-Driven Digital Marketing Internship — 15 Days to 1 Month. "
            "Bootcamp: Python and AI Foundations Bootcamp — 1 Month, Trichy (Hybrid/Offline). "
            "Covers Python, ML, NLP, GenAI, 20+ AI tools: ChatGPT, DALL-E, DeepSeek, GitHub Copilot, Hugging Face."
        ),
        "metadata": {"collection": "internships", "topic": "tracks"},
    },
    # Internship FAQs
    {"id": "faq_internship_available", "text": "Q: Does DigiDARA offer internships?\nA: Yes. We run 15-day to 1-month internships in AI, Data Science, Generative and Agentic AI, Python Full Stack, and AI Digital Marketing. Includes live projects, mentorship, ISO certificate, and LOR for top performers. No prior experience needed. Apply at https://www.digidaratechnologies.com/internships", "metadata": {"collection": "internships", "keywords": "internship available offer"}},
    {"id": "faq_internship_experience", "text": "Q: Do I need prior experience to join an internship?\nA: No prior experience is required. Programs start from basics with expert mentorship at every step.", "metadata": {"collection": "internships", "keywords": "internship experience required prior"}},
    {"id": "faq_internship_projects", "text": "Q: What projects will I work on during the internship?\nA: You will work on AI chatbots, data analytics dashboards, predictive ML models, and Generative AI applications — culminating in a Demo Day capstone presentation.", "metadata": {"collection": "internships", "keywords": "internship projects work build"}},
]

# ─────────────────────────────────────────────────────────────────────────────
# SERVICES collection
# ─────────────────────────────────────────────────────────────────────────────
SERVICES_DOCS: List[KBDocument] = [
    {
        "id": "services_overview",
        "text": (
            "DigiDARA delivers end-to-end AI-powered business solutions for startups, enterprises, and educational institutions. "
            "Four core services: "
            "1. AI-Powered Digital Marketing — content creation, campaign automation, SEO, lead generation. "
            "2. AI Chatbot and Virtual Assistant Development — NLP chatbots for web, WhatsApp, Messenger, CRM. "
            "3. Custom AI Agent Development — LangChain, LangGraph, RAG-based autonomous agents. "
            "4. AI Business Consulting — AI strategy, roadmap, process optimization, responsible AI adoption. "
            "ISO-certified consulting partner. Proven across education, healthcare, retail, finance. "
            "Details: https://www.digidaratechnologies.com/services"
        ),
        "metadata": {"collection": "services", "topic": "overview"},
    },
    {
        "id": "service_digital_marketing",
        "text": (
            "AI-Powered Digital Marketing service: AI-driven content creation (blogs, ad copies, social posts), "
            "campaign personalization using predictive analytics, automated performance dashboards, "
            "ad optimization to maximize reach and reduce cost-per-click. "
            "Ideal for: startups, retail brands, educational institutions, e-commerce. "
            "Tools: ChatGPT, Jasper AI, HubSpot AI, Google Ads AI, Canva, SurferSEO. "
            "Outcome: smarter, data-driven campaigns with improved engagement and conversion rates. "
            "Book free marketing consultation: https://www.digidaratechnologies.com/"
        ),
        "metadata": {"collection": "services", "topic": "digital_marketing"},
    },
    {
        "id": "service_chatbot",
        "text": (
            "AI Chatbot and Virtual Assistant Development: NLP-based chatbots using Gemini and GPT language models. "
            "Multi-platform: Website, WhatsApp, Messenger, Instagram, CRM tools. "
            "Knowledge-based automation for FAQ, support, product recommendations. "
            "Lead capture and intelligent follow-up workflows with auto-response. "
            "Analytics dashboard: conversations, satisfaction scores, response quality. "
            "Ideal for: educational institutions, healthcare, real estate, service businesses, MSMEs. "
            "Tools: LangChain, FastAPI, Dialogflow, Rasa, Gemini API, Twilio, Streamlit. "
            "Outcome: reduced manual support load, increased lead conversion, higher customer satisfaction. "
            "Request chatbot demo: https://www.digidaratechnologies.com/"
        ),
        "metadata": {"collection": "services", "topic": "chatbot"},
    },
    {
        "id": "service_ai_agents",
        "text": (
            "Custom AI Agent Development: Generative and Agentic AI design for multi-step reasoning. "
            "Custom agents: student advisors, HR assistants, CRM copilots, internal automation bots. "
            "LangGraph and LangChain agents connected to APIs, databases, third-party tools. "
            "RAG and Memory systems for context-aware document-trained agents. "
            "Frontend deployment via Streamlit or React. "
            "Tools: LangChain, LangGraph, ChromaDB, FAISS, FastAPI, Streamlit, React. "
            "Outcome: scalable AI ecosystems that enhance efficiency and deliver measurable business outcomes. "
            "URL: https://digidaratechnologies.com/services/ai-agent-development"
        ),
        "metadata": {"collection": "services", "topic": "ai_agents"},
    },
    {
        "id": "service_consulting",
        "text": (
            "AI Business Consulting: AI Strategy and Roadmap — identify automation opportunities and high-impact use cases. "
            "Process Optimization using predictive analytics and smart automation. "
            "Generative AI Integration for customer support, marketing and R&D. "
            "Data Strategy: secure pipelines for storage, labeling and model training. "
            "Responsible AI Adoption: governance frameworks for ethical AI deployment. "
            "Outcome: reduced operational costs, aligned with business goals, sustainable innovation. "
            "Book free consultation: https://www.digidaratechnologies.com/"
        ),
        "metadata": {"collection": "services", "topic": "consulting"},
    },
    {
        "id": "service_results",
        "text": (
            "Proven DigiDARA consulting results: 50% increase in conversion rates for an EdTech SaaS client, "
            "25% improved diagnostic accuracy for a healthcare analytics firm, "
            "35% sales boost for an e-commerce client through AI-driven recommendations."
        ),
        "metadata": {"collection": "services", "topic": "results"},
    },
    # Services FAQs
    {"id": "faq_services_offered", "text": "Q: What AI services does DigiDARA provide for businesses?\nA: We offer four core services: AI-Powered Digital Marketing, AI Chatbot and Virtual Assistant Development, Custom AI Agent Development, and AI Business Consulting. Details at https://www.digidaratechnologies.com/services", "metadata": {"collection": "services", "keywords": "services business offer provide"}},
    {"id": "faq_chatbot_build", "text": "Q: Can DigiDARA build a chatbot or AI agent for my business?\nA: Absolutely. We build NLP-based chatbots for websites and WhatsApp, and custom agentic AI solutions using LangChain, LangGraph, and RAG. Book a free demo at https://www.digidaratechnologies.com/", "metadata": {"collection": "services", "keywords": "build chatbot ai agent business"}},
    {"id": "faq_industries_served", "text": "Q: Which industries does DigiDARA serve?\nA: We serve Education, Healthcare, Manufacturing, Retail, Finance, Startups, and Hospitality. Every solution is customized to the client's tech stack, data, and business goals.", "metadata": {"collection": "services", "keywords": "industries served clients"}},
    {"id": "faq_frameworks", "text": "Q: What AI frameworks and tools does DigiDARA use?\nA: We work with LangChain, LangGraph, RAG using ChromaDB and FAISS, Streamlit, FastAPI, TensorFlow, Keras, Scikit-learn, Gemini API, GPT models, and more.", "metadata": {"collection": "services", "keywords": "frameworks tools langchain langgraph rag"}},
]

# ─────────────────────────────────────────────────────────────────────────────
# PRODUCTS collection
# ─────────────────────────────────────────────────────────────────────────────
PRODUCTS_DOCS: List[KBDocument] = [
    {
        "id": "products_overview",
        "text": (
            "DigiDARA has 6+ proprietary AI products — plug-and-play, battle-tested, ready to deploy. "
            "Trusted by 15+ businesses and educational institutions. "
            "Products page: https://digidaratechnologies.com/products. "
            "1. DigiDARA AI CRM — intelligent CRM with AI-driven insights, automation, predictive analytics. "
            "2. DigiDARA Lead Flux — smart AI lead generation and tracking system. "
            "3. DigiDARA AI Academy — next-generation AI learning platform. "
            "4. DigiDARA AI Career Mate Agent — AI career assistant with personalized learning paths. "
            "5. DigiDARA College GPTs — custom AI assistants for educational institutions. "
            "6. DigiDARA AI Automation Systems — advanced automation tools for business productivity."
        ),
        "metadata": {"collection": "products", "topic": "overview"},
    },
    {
        "id": "product_ai_crm",
        "text": (
            "DigiDARA AI CRM: Intelligent customer relationship management platform powered by AI-driven insights, "
            "automation, and predictive analytics to improve customer engagement and sales performance. "
            "URL: https://digidaratechnologies.com/products/ai-crm"
        ),
        "metadata": {"collection": "products", "topic": "ai_crm"},
    },
    {
        "id": "product_lead_flux",
        "text": (
            "DigiDARA Lead Flux: Smart AI-based lead generation and tracking system that identifies "
            "high-intent prospects and improves conversion efficiency. "
            "URL: https://digidaratechnologies.com/products/lead-flux"
        ),
        "metadata": {"collection": "products", "topic": "lead_flux"},
    },
    {
        "id": "product_ai_academy",
        "text": (
            "DigiDARA AI Academy: Next-generation AI learning platform offering structured programs, "
            "live projects, and industry-aligned technology training. "
            "URL: https://digidaratechnologies.com/products/ai-academy"
        ),
        "metadata": {"collection": "products", "topic": "ai_academy"},
    },
    {
        "id": "product_careermate",
        "text": (
            "DigiDARA AI Career Mate Agent: AI-powered career assistant providing personalized learning paths, "
            "resume optimization, interview preparation, and job readiness guidance. "
            "URL: https://digidaratechnologies.com/products/ai-careermate"
        ),
        "metadata": {"collection": "products", "topic": "careermate"},
    },
    {
        "id": "product_college_gpts",
        "text": (
            "DigiDARA College GPTs: Custom-built AI assistants for educational institutions to automate "
            "student support, communication, and academic workflows. "
            "URL: https://digidaratechnologies.com/products/college-gpts"
        ),
        "metadata": {"collection": "products", "topic": "college_gpts"},
    },
    {
        "id": "product_automation",
        "text": (
            "DigiDARA AI Automation Systems: Advanced AI automation tools that streamline repetitive business tasks, "
            "enhance operational productivity, and reduce manual workload. "
            "URL: https://digidaratechnologies.com/products/ai-automation-systems"
        ),
        "metadata": {"collection": "products", "topic": "automation"},
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# CAREER SUPPORT collection
# ─────────────────────────────────────────────────────────────────────────────
CAREER_DOCS: List[KBDocument] = [
    {
        "id": "career_support_overview",
        "text": (
            "DigiDARA career support continues until every learner is career-ready. "
            "Framework: Skill Mastery → Portfolio Development → Profile Optimization → Mock Interviews → Placement Guidance. "
            "Services: ATS-friendly resume creation and review, LinkedIn optimization (headline, summary, keywords), "
            "1:1 career mentorship with personalized AI career roadmap, mock technical and HR interviews with feedback, "
            "job referrals through DigiDARA Industry Connect Program, "
            "guidance on Google AI and Microsoft Azure AI certifications, "
            "freelancing and startup mentorship for AI ventures. "
            "Example roles: AI Intern, Data Analyst, Machine Learning Engineer, Python Developer, "
            "AI Project Assistant, AI Product Associate."
        ),
        "metadata": {"collection": "career", "topic": "support"},
    },
    {"id": "faq_placement", "text": "Q: Does DigiDARA provide placement and career support?\nA: Yes. Complete career support includes ATS-friendly resume reviews, LinkedIn optimization, 1:1 mentorship, mock interviews both technical and HR, and job referrals through our industry partner network.", "metadata": {"collection": "career", "keywords": "placement career support job"}},
    {"id": "faq_ai_career_india", "text": "Q: Is AI a good career in India?\nA: AI is the fastest-growing technology field in India. DigiDARA Technologies helps students and professionals in Trichy build a career in AI through industry-aligned training and internships.", "metadata": {"collection": "career", "keywords": "ai career india good"}},
    {
        "id": "testimonials",
        "text": (
            "DigiDARA student testimonials: "
            "Dhilruba T (Data Science): 'The trainers explained topics clearly. The founder was very supportive and motivated me throughout.' "
            "Dharshini (Python): 'Friendly trainers, very positive experience, useful for higher studies.' "
            "Gowtham B (Data Analysis Intern): 'Gained hands-on experience with real datasets using Excel, SQL, and Python.' "
            "Priyadharshini: 'I started as an intern and now work as a Junior AI Engineer — DigiDARA's mentorship made the difference.' "
            "Madhunisha: 'My LinkedIn profile optimization helped me land 3 interviews in 2 weeks.' "
            "Keerthika: 'The mock interviews were a game-changer for my confidence.' "
            "Overall rating: 4.9/5 from 10+ verified reviews."
        ),
        "metadata": {"collection": "career", "topic": "testimonials"},
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# PRICING collection — honest placeholder
# ─────────────────────────────────────────────────────────────────────────────
PRICING_DOCS: List[KBDocument] = [
    {
        "id": "pricing_info",
        "text": (
            "Specific pricing and fee details for DigiDARA's courses, internships, and services "
            "are not published publicly and change based on batch and promotional offers. "
            "For current pricing: call +91-95004-06945, WhatsApp https://wa.me/919500406945, "
            "or email support@digidaratechnologies.com. "
            "Group discounts available for 3+ participants. "
            "Free demo class available before enrolling — book at https://www.digidaratechnologies.com/. "
            "Never quote a fee — always direct the customer to contact DigiDARA directly."
        ),
        "metadata": {"collection": "pricing", "topic": "placeholder"},
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# CONTACT collection
# ─────────────────────────────────────────────────────────────────────────────
CONTACT_DOCS: List[KBDocument] = [
    {
        "id": "contact_details",
        "text": (
            "DigiDARA Technologies contact details: "
            "Phone/WhatsApp: +91-95004-06945. "
            "WhatsApp Business: https://wa.me/919500406945. "
            "WhatsApp AI Number: 919843096223. "
            "Email: support@digidaratechnologies.com. "
            "Website: https://www.digidaratechnologies.com. "
            "Address: 2nd Floor, Periyasamy Tower, Near Chathiram Bus Stand, Trichy 620002, Tamil Nadu, India. "
            "Working Hours: Mon–Fri 9:30 AM–7:30 PM | Sat 10 AM–6 PM | Sun Closed. "
            "LinkedIn: https://www.linkedin.com/company/104865843/. "
            "Instagram: https://www.instagram.com/digidara.ai. "
            "Twitter/X: https://x.com/SenthilRaj16078."
        ),
        "metadata": {"collection": "contact", "topic": "details"},
    },
    {
        "id": "book_demo",
        "text": (
            "Book a free demo or consultation with DigiDARA: "
            "1. Free Demo Class — attend a live sample session for any course before enrolling. "
            "   Book at https://www.digidaratechnologies.com/ or WhatsApp +91-95004-06945. Available Mon–Sat 10AM–6PM. "
            "2. Free AI Consulting Consultation — 30-minute 1:1 session with a DigiDARA AI expert. "
            "   Request at https://www.digidaratechnologies.com/ or call +91-95004-06945. By appointment Mon–Sat. "
            "3. Free Career Counseling Session — 1:1 mentor session to identify the right course/internship. "
            "   WhatsApp: Hi Team DigiDARA, I would like to schedule a free career counseling session. "
            "   Available Mon–Sat. "
            "CTA: https://www.digidaratechnologies.com/ | WhatsApp: https://wa.me/919500406945"
        ),
        "metadata": {"collection": "contact", "topic": "book_demo"},
    },
    {"id": "faq_how_to_contact", "text": "Q: How can I contact or enroll with DigiDARA?\nA: Phone: +91-95004-06945 | Email: support@digidaratechnologies.com | Website: https://www.digidaratechnologies.com | WhatsApp: https://wa.me/919500406945 | Address: 2nd Floor, Periyasamy Tower, Trichy 620002 | Hours: Mon–Fri 9:30 AM–7:30 PM, Sat 10 AM–6 PM", "metadata": {"collection": "contact", "keywords": "contact phone email address hours"}},
    {"id": "faq_location", "text": "Q: Where is DigiDARA Technologies located?\nA: 2nd Floor, Periyasamy Tower, Near Chathiram Bus Stand, Trichy 620002, Tamil Nadu, India. Get directions at https://www.digidaratechnologies.com/contact", "metadata": {"collection": "contact", "keywords": "location address where trichy office"}},
    {"id": "faq_book_demo", "text": "Q: How do I book a free demo class or consultation?\nA: Book at https://www.digidaratechnologies.com/, call +91-95004-06945, or WhatsApp at https://wa.me/919500406945. Available Mon–Sat.", "metadata": {"collection": "contact", "keywords": "book demo class consultation free"}},
    {"id": "faq_enroll", "text": "Q: How do I enroll in a DigiDARA course or internship?\nA: Enroll at https://www.digidaratechnologies.com/, call +91-95004-06945, or WhatsApp at https://wa.me/919500406945. You can also visit our Trichy office Mon–Sat.", "metadata": {"collection": "contact", "keywords": "enroll join register sign up how"}},
]

# ─────────────────────────────────────────────────────────────────────────────
# ENROLLMENT collection
# ─────────────────────────────────────────────────────────────────────────────
ENROLLMENT_DOCS: List[KBDocument] = [
    {
        "id": "enrollment_process",
        "text": (
            "How to enroll at DigiDARA Technologies: "
            "1. Visit https://www.digidaratechnologies.com/ and fill the enquiry form, OR "
            "2. Call +91-95004-06945 (Mon–Fri 9:30 AM–7:30 PM, Sat 10 AM–6 PM), OR "
            "3. WhatsApp https://wa.me/919500406945, OR "
            "4. Email support@digidaratechnologies.com, OR "
            "5. Visit the Trichy office: 2nd Floor, Periyasamy Tower, Near Chathiram Bus Stand, Trichy 620002. "
            "Before enrolling: book a free demo class at https://www.digidaratechnologies.com/ to experience teaching quality."
        ),
        "metadata": {"collection": "enrollment", "topic": "process"},
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Combined seed dictionary
# ─────────────────────────────────────────────────────────────────────────────
ALL_SEED_DOCS: Dict[str, List[KBDocument]] = {
    "company": COMPANY_DOCS,
    "founder": FOUNDER_DOCS,
    "courses": COURSES_DOCS,
    "internships": INTERNSHIPS_DOCS,
    "services": SERVICES_DOCS,
    "products": PRODUCTS_DOCS,
    "career": CAREER_DOCS,
    "pricing": PRICING_DOCS,
    "contact": CONTACT_DOCS,
    "enrollment": ENROLLMENT_DOCS,
}

# User-supplied master knowledge, reduced to approved voice-answer chunks.
from app.services.knowledge_uploaded_update import EN_UPDATES
for _collection, _docs in EN_UPDATES.items():
    ALL_SEED_DOCS.setdefault(_collection, []).extend(_docs)

REQUIRED_COLLECTIONS = [
    "company", "founder", "courses", "internships",
    "services", "products", "career", "pricing", "contact", "enrollment",
]

OPTIONAL_COLLECTIONS = ["faq", "case_studies", "policies"]
