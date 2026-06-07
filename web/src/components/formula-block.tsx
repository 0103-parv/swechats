'use client'

import { cn } from '#/lib/utils'
import katex from 'katex'
import { useMemo } from 'react'

export function FormulaBlock({
  latex,
  className,
}: {
  latex: string
  className?: string
}) {
  const html = useMemo(
    () =>
      katex.renderToString(latex, {
        displayMode: true,
        throwOnError: false,
      }),
    [latex],
  )

  return (
    <div
      className={cn(
        'overflow-x-auto rounded-md bg-muted/55 px-3 py-2 text-sm [&_.katex-display]:my-0',
        className,
      )}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
