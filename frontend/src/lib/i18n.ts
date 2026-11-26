export type Lang = 'en' | 'kn' | 'hi'
export const LANGS: { code: Lang; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'kn', label: 'ಕನ್ನಡ' },
  { code: 'hi', label: 'हिन्दी' },
]

const en = {
  dashboard: 'Dashboard', assistant: 'AI Assistant', knowledge: 'Knowledge Base', disease: 'Crop Disease',
  soil: 'Soil Intelligence', farming: 'Smart Farming', schemes: 'Government Schemes', weather: 'Weather & Markets',
  lab: 'LLM Lab', evaluation: 'Evaluation', admin: 'Admin',
  grow: 'Grow', learn: 'Learn', research: 'Research',
  signOut: 'Sign out', theme: 'Switch theme', language: 'Language',
  welcome: 'Namaskara', askPlaceholder: 'Ask about crops, soil, pests, irrigation or schemes…', send: 'Send',
  newChat: 'New conversation', useKb: 'Answer from knowledge base', sources: 'Sources', thinking: 'Reading the knowledge base',
  noChats: 'No conversations yet', upload: 'Upload documents', search: 'Search', searchKb: 'Search the knowledge base',
  analyse: 'Analyse', predict: 'Diagnose leaf', uploadLeaf: 'Drop a leaf photo here or choose a file', confidence: 'Confidence',
  limitations: 'Limitations', recommend: 'Recommend crops', calculate: 'Calculate', season: 'Current season',
  eligibility: 'Eligibility', benefit: 'Benefit', howToApply: 'How to apply', documents: 'Documents needed', officialSite: 'Official website',
  forecast: '7-day forecast', advisories: 'Farm advisories', prices: 'Mandi prices', compare: 'Run comparison',
  login: 'Sign in', register: 'Create account', email: 'Email', password: 'Password', name: 'Full name',
  quickAsk: 'Ask AgriMind', loading: 'Loading…', save: 'Save changes', delete: 'Delete', cancel: 'Cancel',
}

const kn: Partial<typeof en> = {
  dashboard: 'ಡ್ಯಾಶ್‌ಬೋರ್ಡ್', assistant: 'AI ಸಹಾಯಕ', knowledge: 'ಜ್ಞಾನ ಭಂಡಾರ', disease: 'ಬೆಳೆ ರೋಗ',
  soil: 'ಮಣ್ಣಿನ ವಿಶ್ಲೇಷಣೆ', farming: 'ಸ್ಮಾರ್ಟ್ ಕೃಷಿ', schemes: 'ಸರ್ಕಾರಿ ಯೋಜನೆಗಳು', weather: 'ಹವಾಮಾನ ಮತ್ತು ಮಾರುಕಟ್ಟೆ',
  lab: 'LLM ಪ್ರಯೋಗಾಲಯ', evaluation: 'ಮೌಲ್ಯಮಾಪನ', admin: 'ನಿರ್ವಾಹಕ',
  grow: 'ಬೆಳೆಸಿ', learn: 'ಕಲಿಯಿರಿ', research: 'ಸಂಶೋಧನೆ',
  signOut: 'ನಿರ್ಗಮಿಸಿ', theme: 'ಥೀಮ್ ಬದಲಿಸಿ', language: 'ಭಾಷೆ',
  welcome: 'ನಮಸ್ಕಾರ', askPlaceholder: 'ಬೆಳೆ, ಮಣ್ಣು, ಕೀಟ, ನೀರಾವರಿ ಅಥವಾ ಯೋಜನೆಗಳ ಬಗ್ಗೆ ಕೇಳಿ…', send: 'ಕಳುಹಿಸಿ',
  newChat: 'ಹೊಸ ಸಂಭಾಷಣೆ', useKb: 'ಜ್ಞಾನ ಭಂಡಾರದಿಂದ ಉತ್ತರಿಸಿ', sources: 'ಮೂಲಗಳು', thinking: 'ಜ್ಞಾನ ಭಂಡಾರವನ್ನು ಓದುತ್ತಿದೆ',
  noChats: 'ಇನ್ನೂ ಸಂಭಾಷಣೆಗಳಿಲ್ಲ', upload: 'ದಾಖಲೆಗಳನ್ನು ಅಪ್‌ಲೋಡ್ ಮಾಡಿ', search: 'ಹುಡುಕಿ', searchKb: 'ಜ್ಞಾನ ಭಂಡಾರದಲ್ಲಿ ಹುಡುಕಿ',
  analyse: 'ವಿಶ್ಲೇಷಿಸಿ', predict: 'ಎಲೆಯನ್ನು ಪರೀಕ್ಷಿಸಿ', uploadLeaf: 'ಎಲೆಯ ಫೋಟೋವನ್ನು ಇಲ್ಲಿ ಹಾಕಿ ಅಥವಾ ಫೈಲ್ ಆಯ್ಕೆಮಾಡಿ', confidence: 'ವಿಶ್ವಾಸ',
  limitations: 'ಮಿತಿಗಳು', recommend: 'ಬೆಳೆಗಳನ್ನು ಸೂಚಿಸಿ', calculate: 'ಲೆಕ್ಕ ಹಾಕಿ', season: 'ಪ್ರಸ್ತುತ ಋತು',
  eligibility: 'ಅರ್ಹತೆ', benefit: 'ಪ್ರಯೋಜನ', howToApply: 'ಅರ್ಜಿ ಸಲ್ಲಿಸುವುದು ಹೇಗೆ', documents: 'ಅಗತ್ಯ ದಾಖಲೆಗಳು', officialSite: 'ಅಧಿಕೃತ ಜಾಲತಾಣ',
  forecast: '7 ದಿನಗಳ ಮುನ್ಸೂಚನೆ', advisories: 'ಕೃಷಿ ಸಲಹೆಗಳು', prices: 'ಮಂಡಿ ಬೆಲೆಗಳು', compare: 'ಹೋಲಿಕೆ ನಡೆಸಿ',
  login: 'ಪ್ರವೇಶಿಸಿ', register: 'ಖಾತೆ ರಚಿಸಿ', email: 'ಇಮೇಲ್', password: 'ಪಾಸ್‌ವರ್ಡ್', name: 'ಪೂರ್ಣ ಹೆಸರು',
  quickAsk: 'AgriMind ಅನ್ನು ಕೇಳಿ', loading: 'ಲೋಡ್ ಆಗುತ್ತಿದೆ…', save: 'ಉಳಿಸಿ', delete: 'ಅಳಿಸಿ', cancel: 'ರದ್ದುಮಾಡಿ',
}

const hi: Partial<typeof en> = {
  dashboard: 'डैशबोर्ड', assistant: 'AI सहायक', knowledge: 'ज्ञान आधार', disease: 'फसल रोग',
  soil: 'मृदा विश्लेषण', farming: 'स्मार्ट खेती', schemes: 'सरकारी योजनाएँ', weather: 'मौसम और बाज़ार',
  lab: 'LLM प्रयोगशाला', evaluation: 'मूल्यांकन', admin: 'प्रशासन',
  grow: 'उगाएँ', learn: 'सीखें', research: 'शोध',
  signOut: 'साइन आउट', theme: 'थीम बदलें', language: 'भाषा',
  welcome: 'नमस्ते', askPlaceholder: 'फसल, मिट्टी, कीट, सिंचाई या योजनाओं के बारे में पूछें…', send: 'भेजें',
  newChat: 'नई बातचीत', useKb: 'ज्ञान आधार से उत्तर दें', sources: 'स्रोत', thinking: 'ज्ञान आधार पढ़ रहे हैं',
  noChats: 'अभी कोई बातचीत नहीं', upload: 'दस्तावेज़ अपलोड करें', search: 'खोजें', searchKb: 'ज्ञान आधार में खोजें',
  analyse: 'विश्लेषण करें', predict: 'पत्ती की जाँच करें', uploadLeaf: 'पत्ती की फोटो यहाँ डालें या फ़ाइल चुनें', confidence: 'विश्वास',
  limitations: 'सीमाएँ', recommend: 'फसल सुझाएँ', calculate: 'गणना करें', season: 'वर्तमान मौसम',
  eligibility: 'पात्रता', benefit: 'लाभ', howToApply: 'आवेदन कैसे करें', documents: 'आवश्यक दस्तावेज़', officialSite: 'आधिकारिक वेबसाइट',
  forecast: '7 दिन का पूर्वानुमान', advisories: 'कृषि सलाह', prices: 'मंडी भाव', compare: 'तुलना चलाएँ',
  login: 'साइन इन', register: 'खाता बनाएँ', email: 'ईमेल', password: 'पासवर्ड', name: 'पूरा नाम',
  quickAsk: 'AgriMind से पूछें', loading: 'लोड हो रहा है…', save: 'बदलाव सहेजें', delete: 'हटाएँ', cancel: 'रद्द करें',
}

export const dict = { en, kn: kn as typeof en, hi: hi as typeof en }
