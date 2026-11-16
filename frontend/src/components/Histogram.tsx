import { useEffect, useRef } from 'react'

/** RGB histogram computed in the browser from the photo thumbnail. */
export function Histogram({ src }: { src: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    let cancelled = false
    const img = new Image()
    img.decoding = 'async'
    img.src = src
    img.onload = () => {
      if (cancelled || !ref.current) return
      const w = 220
      const h = Math.max(1, Math.round((img.naturalHeight / img.naturalWidth) * w))
      const off = document.createElement('canvas')
      off.width = w
      off.height = h
      const octx = off.getContext('2d', { willReadFrequently: true })
      if (!octx) return
      octx.drawImage(img, 0, 0, w, h)
      const data = octx.getImageData(0, 0, w, h).data
      const bins = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)]
      for (let i = 0; i < data.length; i += 4) {
        bins[0][data[i]]++
        bins[1][data[i + 1]]++
        bins[2][data[i + 2]]++
      }
      const canvas = ref.current
      const dpr = window.devicePixelRatio || 1
      const cw = canvas.clientWidth * dpr
      const ch = canvas.clientHeight * dpr
      canvas.width = cw
      canvas.height = ch
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.clearRect(0, 0, cw, ch)
      const max = Math.max(...bins.map((b) => Math.max(...Array.from(b).slice(2, 254)))) || 1
      const colors = ['rgba(255,70,70,0.65)', 'rgba(70,220,120,0.6)', 'rgba(80,140,255,0.65)']
      ctx.globalCompositeOperation = 'screen'
      bins.forEach((b, c) => {
        ctx.beginPath()
        ctx.moveTo(0, ch)
        for (let x = 0; x < 256; x++) {
          const v = Math.min(1, b[x] / max)
          ctx.lineTo((x / 255) * cw, ch - v * ch * 0.95)
        }
        ctx.lineTo(cw, ch)
        ctx.closePath()
        ctx.fillStyle = colors[c]
        ctx.fill()
      })
    }
    return () => { cancelled = true }
  }, [src])
  return <canvas ref={ref} className="histogram" aria-label="Color histogram" />
}
