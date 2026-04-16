import { LoaderCircle, Plus, X } from 'lucide-react'

function KnowledgeThemeCreateModal({
  open,
  onClose,
  copy,
  createTitle,
  createDescription,
  creating = false,
  onTitleChange,
  onDescriptionChange,
  onCreate,
  error = '',
}) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4 py-6" data-knowledge-hub-create-modal>
      <div className="knowledge-console-panel w-full max-w-2xl overflow-hidden">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 bg-slate-50 px-5 py-5 md:px-6">
          <div>
            <div className="knowledge-console-kicker">{copy.createTitle}</div>
            <div className="mt-3 font-serif text-3xl font-black text-fudan-blue">{copy.createTitle}</div>
            <p className="mt-3 text-sm leading-7 text-slate-600">{copy.createBody}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="knowledge-console-tool-button h-10 w-10 p-0"
            aria-label={copy.close}
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-5 md:px-6">
          {error ? <div className="mb-4 rounded-[0.85rem] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</div> : null}

          <div>
            <label className="knowledge-console-label">{copy.titleLabel}</label>
            <input
              value={createTitle}
              onChange={onTitleChange}
              placeholder={copy.titlePlaceholder}
              className="knowledge-console-input mt-2"
              data-knowledge-hub-create-title
              autoFocus
            />
          </div>

          <div className="mt-4">
            <label className="knowledge-console-label">{copy.descriptionLabel}</label>
            <textarea
              value={createDescription}
              onChange={onDescriptionChange}
              placeholder={copy.descriptionPlaceholder}
              rows={5}
              className="knowledge-console-textarea mt-2 min-h-[9rem] resize-none"
            />
          </div>

          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <button type="button" onClick={onClose} className="knowledge-console-secondary">
              {copy.cancel}
            </button>
            <button
              type="button"
              onClick={onCreate}
              disabled={creating || !createTitle.trim()}
              className="knowledge-console-primary min-w-[8rem] disabled:cursor-not-allowed disabled:opacity-55"
            >
              {creating ? <LoaderCircle size={15} className="animate-spin" /> : <Plus size={15} />}
              {copy.createButton}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default KnowledgeThemeCreateModal
