"""Approved voice-agent chunks derived from the user-supplied English master knowledge.

SEO schemas, chatbot implementation notes and duplicate marketing copy are intentionally
excluded from live retrieval. English and Tamil chunks keep the same fact IDs so the two
language indexes remain aligned and fast.
"""

EN_UPDATES = {
    "company": [
        {"id":"uploaded_company_core","text":"DigiDARA Technologies Private Limited is an ISO-certified AI training and consulting company in Trichy, Tamil Nadu. It specializes in Generative AI, Agentic AI, Data Science, internships and AI business solutions. Its mission is practical project-based AI education and enterprise consulting. Its vision is to make Trichy a global AI hub and empower one million learners and leaders by 2030.","metadata":{"source":"user_master_knowledge","language":"en","topic":"company"}},
    ],
    "courses": [
        {"id":"uploaded_courses_summary","text":"DigiDARA programs include Data Science and Analytics, AI and Machine Learning, Generative and Agentic AI, AI in Digital Marketing, Python Full Stack and AI for Managers. Programs use hands-on labs, mini-projects, a capstone and ISO-aligned certificates. Learning modes can be online, offline or hybrid with live and recorded sessions.","metadata":{"source":"user_master_knowledge","language":"en","topic":"courses"}},
        {"id":"uploaded_ai_systems_engineer","text":"The AI Systems Engineer program is a 12-week curriculum covering AI foundations, LLMs, prompt engineering, RAG, vector databases, multimodal AI, AI agents, LangGraph, MCP, enterprise automation, product development and deployment. It ends with a capstone project and career-readiness support. Registration: https://docs.google.com/forms/d/e/1FAIpQLScctnHY14B_PcqspPw2W1cKCbjz7dg3Ugroh21bSFiCgolABw/viewform?usp=header","metadata":{"source":"user_master_knowledge","language":"en","topic":"ai_systems_engineer"}},
        {"id":"uploaded_business_masterclass","text":"The Business AI Masterclass is for business owners, founders and decision-makers. It covers AI Business Infrastructure, WhatsApp Sales Pipeline automation, LeadFLUX for CEOs and the Scalability Blueprint. Registration: https://docs.google.com/forms/d/e/1FAIpQLSeUiYXbuKWK5crhTPQi3ukUnkjBIdvkjy06IztYl0INoMF6Xg/viewform?usp=header","metadata":{"source":"user_master_knowledge","language":"en","topic":"business_masterclass"}},
    ],
    "internships": [
        {"id":"uploaded_internships","text":"DigiDARA internships run from 15 days to one month in AI, Data Science, Generative and Agentic AI, Python Full Stack and AI Digital Marketing. Each includes two mini-projects, one capstone, mentorship and a certificate. A letter of recommendation is available to top performers. Modes may be online, offline or hybrid.","metadata":{"source":"user_master_knowledge","language":"en","topic":"internships"}},
    ],
    "services": [
        {"id":"uploaded_services","text":"DigiDARA provides AI consulting, custom AI agent development, web and WhatsApp chatbots and AI-powered digital marketing. Solutions may use LangChain, LangGraph, RAG, Chroma or FAISS, React or Streamlit and FastAPI to automate workflows, generate leads, reduce cost and improve measurable ROI.","metadata":{"source":"user_master_knowledge","language":"en","topic":"services"}},
    ],
    "career": [
        {"id":"uploaded_career","text":"Career support includes resume and LinkedIn optimization, mock interviews, one-to-one mentorship and placement guidance or partner referrals. Employment or placement is not guaranteed. The readiness flow is Skill Mastery, Portfolio, Profile Optimization, Mock Interviews and Placement Guidance.","metadata":{"source":"user_master_knowledge","language":"en","topic":"career"}},
    ],
    "founder": [
        {"id":"uploaded_founder","text":"Senthil Rajamarthandan is the Founder and Managing Director of DigiDARA Technologies, with more than 28 years of IT experience across digital transformation, cloud and AI strategy. He leads the company's AI education, AI agent development and enterprise consulting initiatives.","metadata":{"source":"user_master_knowledge","language":"en","topic":"founder"}},
    ],
    "contact": [
        {"id":"uploaded_contact","text":"Contact DigiDARA at +91-95004-06945 or support@digidaratechnologies.com. Office: 2nd Floor, Periyasamy Tower, Near Chathiram Bus Stand, Trichy 620002, Tamil Nadu. Working hours: Monday to Friday 9:30 AM to 7:30 PM; Saturday 10 AM to 6 PM; Sunday closed.","metadata":{"source":"user_master_knowledge","language":"en","topic":"contact"}},
    ],
}

def _ta_doc(collection: str, canonical_id: str, text: str, topic: str):
    """Create one reviewed Tamil voice fact aligned with its English source."""
    return {
        "id": f"ta_{canonical_id}",
        "text": text,
        "metadata": {
            "collection": collection,
            "source": "user_master_knowledge_tamil",
            "language": "ta",
            "topic": topic,
            "canonical_id": canonical_id,
            "register": "spoken_tamil_nadu",
        },
    }


# This is intentionally spoken Tamil, not a literal/document-style translation.
# Technical words commonly used by Tamil Nadu students remain in English so the
# realtime voice can say them naturally and callers can use Tamil or Tanglish.
TA_UPDATES = {
    "company": [
        _ta_doc(
            "company",
            "company_overview",
            "DigiDARA Technologiesன்னா திருச்சியில இருக்கிற ISO-certified AI training மற்றும் consulting company. "
            "2023-ல செந்தில் ராஜமார்த்தாண்டன் ஆரம்பிச்சது. Generative AI, Agentic AI, Data Science training, "
            "internship மற்றும் business-க்கு AI solutions பண்ணித் தர்றாங்க. 5000-க்கும் மேற்பட்ட students-க்கு "
            "training கொடுத்திருக்காங்க; 100-க்கும் மேற்பட்ட live projects பண்ணியிருக்காங்க.",
            "overview",
        ),
        _ta_doc(
            "company",
            "company_mission_vision",
            "DigiDARA-வோட முக்கிய நோக்கம் theory மட்டும் இல்லாம practical project மூலமா AI கற்றுக் கொடுக்கறது. "
            "2030-க்குள் பத்து லட்சம் learners மற்றும் business leaders-ஐ AI-ready ஆக்கணும்; "
            "திருச்சியை ஒரு global AI hub-ஆ உருவாக்கணும்னு vision இருக்கு.",
            "mission_vision",
        ),
    ],
    "founder": [
        _ta_doc(
            "founder",
            "founder_profile",
            "DigiDARA-வோட Founder மற்றும் Managing Director செந்தில் ராஜமார்த்தாண்டன். "
            "HCL Technologies, Cognizant உட்பட IT துறையில 28 வருடத்துக்கும் மேல experience இருக்கு. "
            "Generative AI, Agentic AI, cloud, automation மற்றும் business AI strategy அவரோட முக்கிய expertise.",
            "profile",
        ),
    ],
    "courses": [
        _ta_doc(
            "courses",
            "courses_overview",
            "DigiDARA-ல ஆறு முக்கிய courses இருக்கு: Data Science and Analytics, AI and Machine Learning, "
            "Generative and Agentic AI, AI in Digital Marketing, Python Full Stack, AI for Managers. "
            "இந்த regular courses பொதுவா மூணு மாதம். Online, Trichy offline, hybrid mode இருக்கு. "
            "Hands-on labs, mini projects, capstone project, recordings, certificate மற்றும் placement support சேரும்.",
            "overview",
        ),
        _ta_doc(
            "courses",
            "course_data_science",
            "Data Science and Analytics course மூணு மாதம். Python, Pandas, NumPy, data cleaning, EDA, "
            "statistics, Power BI, Tableau மற்றும் business projects கற்றுக் கொடுப்பாங்க. Online, offline, hybrid mode இருக்கு.",
            "data_science",
        ),
        _ta_doc(
            "courses",
            "course_ai_ml",
            "AI and Machine Learning course மூணு மாதம். ML basics, supervised மற்றும் unsupervised learning, "
            "deep learning, neural networks, model training மற்றும் deployment கற்றுக் கொடுப்பாங்க. "
            "TensorFlow, Keras, Scikit-learn மாதிரி tools use பண்ணுவாங்க.",
            "ai_ml",
        ),
        _ta_doc(
            "courses",
            "course_genai_agentic",
            "Generative AI and Agentic AI course மூணு மாதம். Prompt engineering, RAG, ChromaDB, FAISS, "
            "LangChain, LangGraph, agent memory, planning, Streamlit மற்றும் FastAPI deployment வரை practical-ஆ கற்றுக் கொடுப்பாங்க.",
            "genai_agentic",
        ),
        _ta_doc(
            "courses",
            "course_digital_marketing",
            "AI in Digital Marketing course மூணு மாதம். Content creation, campaign automation, audience targeting, "
            "social media analytics, ads, WhatsApp மற்றும் email marketing automation கற்றுக் கொடுப்பாங்க.",
            "digital_marketing",
        ),
        _ta_doc(
            "courses",
            "course_python_fullstack",
            "Python Full Stack course மூணு மாதம். HTML, CSS, JavaScript, React frontend; Python, Flask, Django backend; "
            "SQL, NoSQL, API integration, authentication மற்றும் cloud deployment கற்றுக் கொடுப்பாங்க.",
            "python_fullstack",
        ),
        _ta_doc(
            "courses",
            "course_ai_managers",
            "AI for Managers and Business Leaders course மூணு மாதம். Business-ல AI வாய்ப்பை identify பண்ணறது, "
            "AI strategy, data governance, ethical AI மற்றும் transformation roadmap கற்றுக் கொடுப்பாங்க.",
            "ai_managers",
        ),
        _ta_doc(
            "courses",
            "uploaded_ai_systems_engineer",
            "AI Systems Engineer program பன்னிரண்டு வாரம். AI foundations, LLMs, prompt engineering, RAG, "
            "vector database, multimodal AI, AI agents, LangGraph, MCP, automation, product development மற்றும் deployment இருக்கு. "
            "கடைசியில capstone project மற்றும் career-readiness support கிடைக்கும்.",
            "ai_systems_engineer",
        ),
        _ta_doc(
            "courses",
            "uploaded_business_masterclass",
            "Business AI Masterclass business owners, founders மற்றும் decision makers-க்கான program. "
            "AI business infrastructure, WhatsApp sales pipeline automation, LeadFLUX மற்றும் scalability blueprint பற்றி இருக்கும்.",
            "business_masterclass",
        ),
    ],
    "internships": [
        _ta_doc(
            "internships",
            "internship_overview",
            "DigiDARA internship 15 நாள் முதல் ஒரு மாதம் வரை இருக்கும். இரண்டு mini projects, ஒரு capstone project, "
            "one-to-one mentorship, weekly review, certificate, GitHub portfolio guidance மற்றும் mock interview support கிடைக்கும். "
            "Top performers-க்கு Letter of Recommendation கிடைக்கலாம்; அது எல்லாருக்கும் guarantee இல்லை.",
            "overview",
        ),
        _ta_doc(
            "internships",
            "internship_tracks",
            "Data Science, AI and Machine Learning, Generative and Agentic AI internships ஒரு மாதம். "
            "Python Full Stack மற்றும் AI Digital Marketing internship 15 நாள் முதல் ஒரு மாதம். "
            "Online, Trichy offline அல்லது hybrid mode batch-ஐப் பொறுத்து இருக்கும்.",
            "tracks",
        ),
    ],
    "services": [
        _ta_doc(
            "services",
            "services_overview",
            "Business-க்கு DigiDARA AI digital marketing, web அல்லது WhatsApp chatbot, custom AI agent development "
            "மற்றும் AI consulting பண்ணித் தர்றாங்க. Startup, company, college தேவைக்கேற்ற மாதிரி workflow automation, "
            "lead generation மற்றும் support solutions customize பண்ணலாம்.",
            "overview",
        ),
    ],
    "products": [
        _ta_doc(
            "products",
            "products_overview",
            "DigiDARA products-ல AI CRM, Lead Flux lead tracking system, AI Academy, Career Mate, "
            "College GPTs மற்றும் business automation systems இருக்கு. Customer need தெரிஞ்ச பிறகு சரியான product-ஐ team suggest பண்ணுவாங்க.",
            "overview",
        ),
    ],
    "career": [
        _ta_doc(
            "career",
            "career_support_overview",
            "Career support-ல ATS-friendly resume, LinkedIn profile optimization, portfolio guidance, one-to-one mentorship, "
            "mock technical மற்றும் HR interview, placement guidance, partner referral support இருக்கு. "
            "வேலை அல்லது placement guarantee கிடையாது; opportunity-க்கு prepare ஆக support பண்ணுவாங்க.",
            "overview",
        ),
    ],
    "pricing": [
        _ta_doc(
            "pricing",
            "pricing_info",
            "Course மற்றும் internship fees batch, offer-ஐப் பொறுத்து மாறலாம்; public-ஆ fixed fees publish பண்ணல. "
            "அதனால எந்த amount-யும் guess பண்ணக்கூடாது. Exact fees-ஐ counsellor தான் confirm பண்ணுவாங்க. "
            "மூணு பேருக்கு மேல group-ஆ join பண்ணினா discount இருக்கலாம். Enroll பண்ணுறதுக்கு முன்னாடி free demo கேட்கலாம்.",
            "pricing_guardrail",
        ),
    ],
    "contact": [
        _ta_doc(
            "contact",
            "contact_details",
            "DigiDARA phone மற்றும் WhatsApp number: +91 95004 06945. Email: support@digidaratechnologies.com. "
            "Office: second floor, Periyasamy Tower, Chathiram Bus Stand பக்கத்துல, Trichy 620002. "
            "Monday முதல் Friday காலை 9:30 முதல் மாலை 7:30 வரை; Saturday காலை 10 முதல் மாலை 6 வரை; Sunday leave.",
            "details",
        ),
        _ta_doc(
            "contact",
            "book_demo",
            "Free demo class, AI consultation அல்லது career counselling book பண்ண website enquiry form use பண்ணலாம், "
            "இல்லனா +91 95004 06945-க்கு call அல்லது WhatsApp பண்ணலாம். Demo மற்றும் consultation appointment, batch availability-ஐப் பொறுத்தது.",
            "book_demo",
        ),
    ],
    "enrollment": [
        _ta_doc(
            "enrollment",
            "enrollment_process",
            "Course அல்லது internship join பண்ண website-ல enquiry form fill பண்ணலாம்; "
            "+91 95004 06945-க்கு call அல்லது WhatsApp பண்ணலாம்; support@digidaratechnologies.com-க்கு mail அனுப்பலாம்; "
            "இல்லனா Trichy office-க்கு நேர்ல போகலாம். Final batch date மற்றும் fees-ஐ counsellor confirm பண்ணுவாங்க.",
            "process",
        ),
    ],
}


# Complete semantic parity for the non-duplicate facts in the English master
# knowledge. These are deliberately short spoken-Tamil chunks: retrieval can
# select the exact fact without pushing a long document-style translation into
# every Realtime turn.
TA_PARITY_UPDATES = {
    "company": [
        _ta_doc(
            "company", "company_certifications",
            "DigiDARA Technologies-க்கு ISO 9001:2015 quality management, ISO 27001:2013 information security, "
            "ISO 20000-1:2018 IT service management certifications இருக்கு. எல்லா training program மற்றும் "
            "internship-க்கும் ISO-aligned DigiDARA certificate கொடுக்கப்படும்.",
            "certifications",
        ),
        _ta_doc(
            "company", "company_unique",
            "DigiDARA students, educators, working professionals எல்லாருக்கும் practical-ஆ AI கற்றுக் கொடுக்கிறது. "
            "ஒவ்வொரு module-லும் live project அல்லது AI agent prototype, industry-aligned learning, experienced AI "
            "architect mentorship மற்றும் responsible AI practice இருக்கும். Engineering college, SME, retail, "
            "e-commerce, healthcare, digital agency, finance, consulting sectors-க்கு solutions கொடுக்கிறாங்க.",
            "unique_value",
        ),
        _ta_doc(
            "company", "company_impact",
            "DigiDARA இதுவரை 5000-க்கும் மேற்பட்ட students-க்கு training, 100-க்கும் மேற்பட்ட live projects, "
            "50-க்கும் மேற்பட்ட college மற்றும் industry partnerships செய்திருக்கிறது. 6-க்கும் மேற்பட்ட AI agents, "
            "6 proprietary products, 4 AI services, 15-க்கும் மேற்பட்ட business clients மற்றும் 4.9 out of 5 "
            "verified review rating இருக்கு.",
            "impact",
        ),
    ],
    "founder": [
        _ta_doc(
            "founder", "founder_motivation",
            "Academic learning-க்கும் industry readiness-க்கும் இருக்கிற gap-ஐ குறைத்து, இந்தியாவில் எல்லாருக்கும் "
            "practical AI education கிடைக்கணும்னு செந்தில் ராஜமார்த்தாண்டன் DigiDARA-வை ஆரம்பித்தார்.",
            "motivation",
        ),
        _ta_doc(
            "founder", "founder_ai_agents",
            "DigiDARA உருவாக்கிய AI agents-ல் student information-க்கான EduMate, resume மற்றும் HR support-க்கான "
            "CareerMate, knowledge search-க்கான InfoMate, productivity-க்கான MindMate, food service-க்கான "
            "CanteenMate மற்றும் lead-tracking business chatbots இருக்கு.",
            "ai_agents",
        ),
    ],
    "courses": [
        _ta_doc(
            "courses", "courses_beginner_fit",
            "DigiDARA courses beginners-க்கும் suitable. Foundation concepts-ல ஆரம்பித்து step-by-step advanced "
            "hands-on projects வரை போவதால் students, working professionals மற்றும் upskill பண்ணுறவங்க join பண்ணலாம்.",
            "beginner_fit",
        ),
        _ta_doc(
            "courses", "courses_projects_certificate",
            "ஒவ்வொரு regular program-லும் hands-on labs, real-world mini projects, ஒரு capstone project மற்றும் "
            "ISO-aligned DigiDARA certificate இருக்கும். Career support availability program-ஐப் பொறுத்து counsellor "
            "confirm பண்ணுவாங்க; வேலை guarantee கிடையாது.",
            "projects_certificate",
        ),
        _ta_doc(
            "courses", "courses_group_corporate",
            "மூன்று பேர் அல்லது அதற்கு மேல் group-ஆ join பண்ணினால் group discount இருக்கலாம். Companies-க்கு அவர்களோட "
            "business need-க்கு ஏற்ற custom corporate AI training-மும் arrange பண்ணலாம்; exact proposal-ஐ team confirm பண்ணும்.",
            "group_corporate",
        ),
        _ta_doc(
            "courses", "course_registration_links",
            "AI Systems Engineer registration form: https://docs.google.com/forms/d/e/1FAIpQLScctnHY14B_PcqspPw2W1cKCbjz7dg3Ugroh21bSFiCgolABw/viewform?usp=header . "
            "Business AI Masterclass registration form: https://docs.google.com/forms/d/e/1FAIpQLSeUiYXbuKWK5crhTPQi3ukUnkjBIdvkjy06IztYl0INoMF6Xg/viewform?usp=header . "
            "Phone call-ல் URL-ஐ வாசிக்காமல், customer கேட்டால் WhatsApp-ல் link share பண்ண counsellor callback offer பண்ணவும்.",
            "registration",
        ),
    ],
    "internships": [
        _ta_doc(
            "internships", "internship_beginner_fit",
            "Internship join பண்ண prior experience கட்டாயம் இல்லை. Basics-ல ஆரம்பித்து mentor step-by-step guide "
            "பண்ணுவாங்க; exact track மற்றும் batch eligibility-ஐ counsellor confirm பண்ணுவாங்க.",
            "beginner_fit",
        ),
        _ta_doc(
            "internships", "internship_project_examples",
            "Internship projects-ல் AI chatbot, data analytics dashboard, predictive Machine Learning model மற்றும் "
            "Generative AI application மாதிரி practical work இருக்கலாம். கடைசியில் capstone-ஐ Demo Day-ல் present பண்ணும் flow இருக்கும்.",
            "projects",
        ),
    ],
    "services": [
        _ta_doc(
            "services", "service_digital_marketing",
            "AI Digital Marketing service-ல் blog, ad copy, social post content creation, predictive campaign "
            "personalization, automated performance dashboard மற்றும் ad optimization செய்யலாம். Startup, retail, "
            "education, e-commerce business-க்கு engagement மற்றும் conversion improve பண்ணுவது இதோட நோக்கம்.",
            "digital_marketing",
        ),
        _ta_doc(
            "services", "service_chatbot",
            "DigiDARA website, WhatsApp, Messenger, Instagram மற்றும் CRM-க்கு GPT அல்லது Gemini-based chatbot build "
            "பண்ணும். FAQ support, product recommendation, lead capture, automatic follow-up மற்றும் conversation "
            "analytics சேர்க்கலாம். Final scope customer requirement review பண்ணிய பிறகுதான் confirm ஆகும்.",
            "chatbot",
        ),
        _ta_doc(
            "services", "service_ai_agents",
            "Custom AI agent service-ல் student advisor, HR assistant, CRM copilot மற்றும் workflow automation bot "
            "உருவாக்கலாம். LangChain, LangGraph, RAG, ChromaDB, FAISS, API, database integration, memory மற்றும் "
            "React அல்லது Streamlit frontend use பண்ணலாம்.",
            "ai_agents",
        ),
        _ta_doc(
            "services", "service_consulting",
            "AI Business Consulting-ல் automation வாய்ப்புகளை identify பண்ணுவது, AI strategy மற்றும் roadmap, process "
            "optimization, Generative AI integration, secure data pipeline மற்றும் responsible AI governance பற்றி "
            "team ஆலோசனை கொடுக்கும். Scope-க்கு பிறகு feasibility மற்றும் proposal confirm ஆகும்.",
            "consulting",
        ),
        _ta_doc(
            "services", "service_results",
            "Published DigiDARA case results-ல் EdTech SaaS client-க்கு conversion 50 percent உயர்வு, healthcare "
            "analytics firm-க்கு diagnostic accuracy 25 percent improvement, e-commerce client-க்கு AI recommendation "
            "மூலம் sales 35 percent உயர்வு reported ஆகியிருக்கு. இது past result; future result guarantee இல்லை.",
            "results",
        ),
        _ta_doc(
            "services", "service_industries",
            "DigiDARA Education, Healthcare, Manufacturing, Retail, Finance, Startup மற்றும் Hospitality industries-க்கு "
            "AI solutions செய்கிறது. ஒவ்வொரு solution-மும் customer tech stack, data மற்றும் business goal-க்கு ஏற்ற மாதிரி customize ஆகும்.",
            "industries",
        ),
        _ta_doc(
            "services", "service_frameworks",
            "DigiDARA use பண்ணும் technologies-ல் LangChain, LangGraph, RAG, ChromaDB, FAISS, Streamlit, FastAPI, "
            "TensorFlow, Keras, Scikit-learn, Gemini API மற்றும் GPT models இருக்கு. Project-க்கு சரியான tool-ஐ technical team தேர்வு செய்யும்.",
            "frameworks",
        ),
    ],
    "products": [
        _ta_doc(
            "products", "product_ai_crm",
            "DigiDARA AI CRM customer engagement மற்றும் sales performance improve பண்ண AI insights, automation மற்றும் "
            "predictive analytics use பண்ணும் customer relationship platform.",
            "ai_crm",
        ),
        _ta_doc(
            "products", "product_lead_flux",
            "Lead Flux என்பது high-intent prospects-ஐ identify பண்ணி leads-ஐ track செய்து conversion efficiency improve "
            "பண்ண உதவும் AI-based lead generation மற்றும் tracking system.",
            "lead_flux",
        ),
        _ta_doc(
            "products", "product_ai_academy",
            "DigiDARA AI Academy structured learning programs, live projects மற்றும் industry-aligned technology training "
            "கொடுக்கிற AI learning platform.",
            "ai_academy",
        ),
        _ta_doc(
            "products", "product_careermate",
            "AI Career Mate personalized learning path, resume optimization, interview preparation மற்றும் job-readiness "
            "guidance கொடுக்கிற career assistant.",
            "careermate",
        ),
        _ta_doc(
            "products", "product_college_gpts",
            "College GPTs educational institutions-க்காக student support, communication மற்றும் academic workflows-ஐ "
            "automate பண்ண custom-ஆ build செய்யப்படும் AI assistants.",
            "college_gpts",
        ),
        _ta_doc(
            "products", "product_automation",
            "DigiDARA AI Automation Systems repetitive business tasks-ஐ streamline பண்ணி productivity improve செய்யவும் "
            "manual workload குறைக்கவும் உருவாக்கப்படும் automation tools.",
            "automation",
        ),
    ],
    "career": [
        _ta_doc(
            "career", "career_ai_india",
            "AI இந்தியாவில் வேகமாக வளர்கிற technology field. Industry-aligned training, practical projects, internship, "
            "portfolio மற்றும் interview preparation சரியாக செய்தால் AI career-க்கு prepare ஆகலாம்; வேலை கிடைக்கும் என்று guarantee சொல்ல முடியாது.",
            "ai_career_india",
        ),
        _ta_doc(
            "career", "career_testimonials",
            "Verified student feedback-ல் trainers topics-ஐ clear-ஆ explain பண்ணியது, real dataset-ல் Excel, SQL, Python "
            "hands-on experience, supportive mentorship, LinkedIn optimization மற்றும் mock interview confidence பற்றி "
            "positive-ஆ சொல்லியிருக்காங்க. Overall published rating 4.9 out of 5 from 10-க்கும் மேற்பட்ட verified reviews.",
            "testimonials",
        ),
    ],
    "contact": [
        _ta_doc(
            "contact", "contact_web_channels",
            "DigiDARA website https://www.digidaratechnologies.com . Course, internship, service மற்றும் free demo enquiry "
            "website form-ல் submit பண்ணலாம். Phone அல்லது WhatsApp +91 95004 06945; email support@digidaratechnologies.com. "
            "Call-ல் URL அல்லது email-ஐ customer கேட்டால் மட்டும் மெதுவாக சொல்லவும்; இல்லனா WhatsApp share offer பண்ணவும்.",
            "web_channels",
        ),
    ],
}

for _collection, _documents in TA_PARITY_UPDATES.items():
    TA_UPDATES.setdefault(_collection, []).extend(_documents)
