import type { CSSProperties, MouseEvent, ReactNode } from 'react'

const MATTE = ['matte', 'premium-matte', 'fine-art-smooth', 'fine-art-rough', 'canvas', 'washi', 'plain']

/**
 * A photo shown as the physical sheet it will become: true page aspect ratio,
 * square corners, a contact shadow and a sheen that follows the paper finish.
 */
export function PrintSheet({ src, aspect, finish, sheen = 0.5, tint, maxHeight, maxWidth, width, className, children, onClick, alt, eject }: {
  src?: string | null
  aspect: number
  finish?: string
  sheen?: number
  tint?: string
  maxHeight?: number | string
  maxWidth?: number | string
  width?: number | string
  className?: string
  children?: ReactNode
  onClick?: (e: MouseEvent<HTMLDivElement>) => void
  alt?: string
  eject?: boolean
}) {
  const matte = finish ? MATTE.includes(finish) : false
  const style: CSSProperties = {
    aspectRatio: String(aspect),
    maxWidth,
    width: width ?? '100%',
    ['--sheet-tint' as string]: tint ?? '#fbfbf9',
    ['--sheen' as string]: matte ? 1 : Math.max(0.15, sheen),
  }
  if (maxHeight && !width) {
    // fit inside max height while keeping the true paper aspect ratio
    const h = typeof maxHeight === 'number' ? `${maxHeight}px` : maxHeight
    style.width = `min(100%, calc(${h} * ${aspect}))`
  }
  return (
    <div className={`sheet${matte ? ' matte' : ''}${eject ? ' eject' : ''}${className ? ` ${className}` : ''}`} style={style} onClick={onClick}>
      {src ? <img src={src} alt={alt ?? ''} draggable={false} /> : null}
      {children}
    </div>
  )
}
