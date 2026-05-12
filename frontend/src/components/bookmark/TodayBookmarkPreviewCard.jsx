import { BookOpen, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

function TodayBookmarkPreviewCard({ bookmark, isEnglish = false }) {
  const available = Boolean(bookmark?.available)
  const displayTheme = bookmark?.headline_theme || bookmark?.primary_theme || (isEnglish ? 'Today' : '今日')

  return (
    <section className="today-bookmark-preview-card fudan-panel overflow-hidden">
      <div className="grid gap-6 lg:grid-cols-[0.88fr_1.12fr]">
        <div className="border-b border-slate-200 bg-[linear-gradient(145deg,rgba(13,7,131,0.96),rgba(10,5,96,0.9)_58%,rgba(234,107,0,0.22))] px-8 py-8 text-white lg:border-b-0 lg:border-r">
          <div className="section-kicker !text-white/70">{isEnglish ? 'Today Bookmark' : '今日书签'}</div>
          <h2 className="font-serif text-4xl font-black leading-tight text-white md:text-5xl">
            {available ? displayTheme : isEnglish ? 'No reading yet' : '今日暂无阅读'}
          </h2>
          <p className="mt-4 text-sm leading-8 text-white/82">
            {available
              ? isEnglish
                ? 'A visual bookmark generated from everything you read today. Drag the core theme and watch the text reflow around it.'
                : '从你今天真正看过的文章里抽取文本，生成一张可拖动主题词的个人化书签。'
              : bookmark?.empty_message || (isEnglish ? 'Read a few articles first, then come back for your daily bookmark.' : '先读几篇文章，再回来生成今天的书签。')}
          </p>
          <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-white/18 bg-white/10 px-4 py-2 text-sm font-semibold text-white">
            <Sparkles size={15} />
            {bookmark?.date_label} {bookmark?.weekday_label}
          </div>
        </div>

        <div className="px-8 py-8">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-[1.35rem] border border-slate-200 bg-slate-50 px-5 py-5">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-400">{isEnglish ? 'Theme' : '主题'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-fudan-blue">{displayTheme || (isEnglish ? 'Pending' : '待生成')}</div>
            </div>
            <div className="rounded-[1.35rem] border border-slate-200 bg-slate-50 px-5 py-5">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-400">{isEnglish ? 'Articles today' : '今日文章'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-fudan-blue">{bookmark?.article_count || 0}</div>
            </div>
            <div className="rounded-[1.35rem] border border-slate-200 bg-slate-50 px-5 py-5">
              <div className="text-xs uppercase tracking-[0.22em] text-slate-400">{isEnglish ? 'Phrases' : '短语池'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-fudan-blue">{bookmark?.phrases?.length || 0}</div>
            </div>
          </div>

          <div className="mt-6 rounded-[1.6rem] border border-slate-200 bg-white p-6">
            <div className="text-xs uppercase tracking-[0.22em] text-fudan-orange">{isEnglish ? 'Reason' : '主题说明'}</div>
            <p className="mt-3 text-sm leading-7 text-slate-600">
              {bookmark?.theme_reason ||
                (isEnglish
                  ? 'The system will consolidate today’s reading into one dominant theme before generating the bookmark.'
                  : '系统会先把你今天阅读的内容压缩成一个主主题，再生成书签。')}
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/me/today-bookmark" className="knowledge-console-primary">
                <BookOpen size={16} />
                {isEnglish ? 'Open bookmark' : '打开书签'}
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

export default TodayBookmarkPreviewCard
