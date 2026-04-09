import ChatPanel from '../components/shared/ChatPanel.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'

function ChatPage() {
  const { isEnglish } = useLanguage()

  return (
    <div className="page-shell py-12">
      <div className="mb-8">
        <div className="section-kicker">{isEnglish ? 'AI Assistant' : 'AI \u52a9\u7406'}</div>
        <h1 className="section-title">
          {isEnglish ? 'Ask, compare, and synthesize across the knowledge base' : '\u56f4\u7ed5\u77e5\u8bc6\u5e93\u7ee7\u7eed\u63d0\u95ee\u3001\u6bd4\u8f83\u4e0e\u6574\u5408'}
        </h1>
      </div>
      <ChatPanel variant="page" />
    </div>
  )
}

export default ChatPage
