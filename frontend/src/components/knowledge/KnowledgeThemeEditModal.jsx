import { LoaderCircle, PencilLine, X } from 'lucide-react'

function KnowledgeThemeEditModal({
  open,
  onClose,
  onSave,
  saving = false,
  titleValue,
  descriptionValue,
  onTitleChange,
  onDescriptionChange,
  copy,
  error = '',
}) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-6" data-knowledge-theme-rename-modal>
      <div className="knowledge-console-panel w-full max-w-2xl overflow-hidden">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 bg-slate-50 px-5 py-5 md:px-6">
          <div>
            <div className="knowledge-console-kicker">{copy.edit}</div>
            <div className="mt-3 font-serif text-3xl font-black text-fudan-blue">{copy.edit}</div>
          </div>
          <button type="button" onClick={onClose} className="knowledge-console-tool-button h-10 w-10 p-0" aria-label={copy.close}>
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-5 md:px-6">
          {error ? <div className="mb-4 rounded-[0.85rem] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</div> : null}

          <div>
            <label className="knowledge-console-label">{copy.renameTitle}</label>
            <input
              value={titleValue}
              onChange={onTitleChange}
              className="knowledge-console-input mt-2"
              data-knowledge-theme-rename-title
              autoFocus
            />
          </div>

          <div className="mt-4">
            <label className="knowledge-console-label">{copy.renameNote}</label>
            <textarea
              value={descriptionValue}
              onChange={onDescriptionChange}
              rows={5}
              className="knowledge-console-textarea mt-2 min-h-[9rem] resize-none"
              data-knowledge-theme-rename-description
            />
          </div>

          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <button type="button" onClick={onClose} className="knowledge-console-secondary">
              {copy.cancel}
            </button>
            <button
              type="button"
              onClick={onSave}
              disabled={saving || !String(titleValue || '').trim()}
              className="knowledge-console-primary min-w-[8rem] disabled:cursor-not-allowed disabled:opacity-55"
              data-knowledge-theme-rename-save
            >
              {saving ? <LoaderCircle size={15} className="animate-spin" /> : <PencilLine size={15} />}
              {copy.save}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default KnowledgeThemeEditModal
