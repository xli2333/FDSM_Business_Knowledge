import { Link } from 'react-router-dom'
import { useLanguage } from '../../i18n/LanguageContext.js'

function Footer() {
  const { t } = useLanguage()

  return (
    <footer className="mt-20 border-t border-slate-200/70 bg-white/80">
      <div className="page-shell flex flex-col gap-6 py-10 text-sm text-slate-500 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="font-serif text-2xl font-bold text-fudan-blue">{t('appName')}</div>
          <p className="mt-2 max-w-2xl leading-7">{t('footer.description')}</p>
        </div>

        <div className="flex flex-col items-start gap-3 md:items-end">
          <Link
            to="/commercial"
            className="inline-flex items-center rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
          >
            {t('footer.commercial')}
          </Link>
          <div className="text-xs uppercase tracking-[0.28em] text-slate-400">Fudan Blue × Fudan Orange</div>
        </div>
      </div>
    </footer>
  )
}

export default Footer
