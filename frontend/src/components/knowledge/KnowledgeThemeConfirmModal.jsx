import { LoaderCircle, Trash2, X } from 'lucide-react'

function KnowledgeThemeConfirmModal({
  open,
  onClose,
  onConfirm,
  confirming = false,
  title = '',
  body = '',
  confirmLabel = '确认',
  cancelLabel = '取消',
  closeLabel = '关闭',
  dataScope = 'knowledge-confirm-modal',
  error = '',
}) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-6" data-knowledge-confirm-modal={dataScope}>
      <div className="knowledge-console-panel w-full max-w-xl overflow-hidden">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 bg-slate-50 px-5 py-5 md:px-6">
          <div>
            <div className="knowledge-console-kicker">确认操作</div>
            <div className="mt-3 font-serif text-3xl font-black text-fudan-blue">{title}</div>
          </div>
          <button type="button" onClick={onClose} className="knowledge-console-tool-button h-10 w-10 p-0" aria-label={closeLabel}>
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-5 md:px-6">
          {body ? <p className="text-sm leading-7 text-slate-600">{body}</p> : null}
          {error ? <div className="mt-4 rounded-[0.85rem] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</div> : null}

          <div className="mt-6 flex flex-wrap justify-end gap-2">
            <button type="button" onClick={onClose} className="knowledge-console-secondary">
              {cancelLabel}
            </button>
            <button
              type="button"
              onClick={onConfirm}
              disabled={confirming}
              className="inline-flex min-w-[8rem] items-center justify-center gap-2 rounded-[0.8rem] border border-rose-500 bg-rose-500 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-rose-600 disabled:cursor-not-allowed disabled:opacity-55"
              data-knowledge-confirm-submit={dataScope}
            >
              {confirming ? <LoaderCircle size={15} className="animate-spin" /> : <Trash2 size={15} />}
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default KnowledgeThemeConfirmModal
