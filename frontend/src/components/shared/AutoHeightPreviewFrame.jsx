import { useEffect, useRef } from 'react'

function AutoHeightPreviewFrame({ title, srcDoc, minHeight = 200, className = '' }) {
  const frameRef = useRef(null)

  useEffect(() => {
    const iframe = frameRef.current
    if (!iframe) return undefined

    let resizeObserver = null
    let frameWindow = null

    const syncHeight = () => {
      const doc = iframe.contentDocument
      if (!doc) return
      const bodyHeight = doc.body?.scrollHeight || 0
      const htmlHeight = doc.documentElement?.scrollHeight || 0
      iframe.style.height = `${Math.max(minHeight, bodyHeight, htmlHeight)}px`
    }

    const attachResizeTracking = () => {
      const doc = iframe.contentDocument
      if (!doc) return
      syncHeight()
      frameWindow = iframe.contentWindow
      frameWindow?.addEventListener('resize', syncHeight)

      if ('ResizeObserver' in window) {
        resizeObserver = new window.ResizeObserver(() => {
          window.requestAnimationFrame(syncHeight)
        })
        if (doc.body) resizeObserver.observe(doc.body)
        if (doc.documentElement) resizeObserver.observe(doc.documentElement)
      }

      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(syncHeight)
      })
    }

    iframe.addEventListener('load', attachResizeTracking)
    if (iframe.contentDocument?.readyState === 'complete') {
      attachResizeTracking()
    }

    return () => {
      iframe.removeEventListener('load', attachResizeTracking)
      frameWindow?.removeEventListener('resize', syncHeight)
      resizeObserver?.disconnect()
    }
  }, [minHeight, srcDoc])

  return (
    <iframe
      ref={frameRef}
      title={title}
      srcDoc={srcDoc}
      scrolling="no"
      sandbox="allow-same-origin"
      className={className}
    />
  )
}

export default AutoHeightPreviewFrame
