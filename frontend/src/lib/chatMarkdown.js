function markerPairScore(positions) {
  let score = 0
  for (let index = 0; index < positions.length; index += 2) {
    if (Number.isInteger(positions[index + 1])) {
      score += positions[index + 1] - positions[index]
    }
  }
  return score
}

function removeMostLikelyUnmatchedMarker(value, marker) {
  const text = String(value || '')
  const pattern = new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')
  const positions = [...text.matchAll(pattern)].map((match) => match.index).filter((index) => Number.isInteger(index))
  if (!positions.length || positions.length % 2 === 0) return text
  if (positions.length === 1) {
    const onlyIndex = positions[0]
    return text.slice(0, onlyIndex) + text.slice(onlyIndex + marker.length)
  }
  const dropFirstScore = markerPairScore(positions.slice(1))
  const dropLastScore = markerPairScore(positions.slice(0, -1))
  const index = dropFirstScore <= dropLastScore ? positions[0] : positions[positions.length - 1]
  return text.slice(0, index) + text.slice(index + marker.length)
}

function findSingleMarkerPositions(text) {
  const value = String(text || '')
  const positions = []
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] !== '*') continue
    if (value[index - 1] === '*' || value[index + 1] === '*') continue
    const prefix = value.slice(0, index)
    if ((!prefix.trim() || /^[\s>]+$/.test(prefix)) && value[index + 1] === ' ') continue
    positions.push(index)
  }
  return positions
}

function removeMostLikelyUnmatchedSingleMarker(value) {
  const text = String(value || '')
  const positions = findSingleMarkerPositions(text)
  if (!positions.length || positions.length % 2 === 0) return text
  if (positions.length === 1) {
    const onlyIndex = positions[0]
    return text.slice(0, onlyIndex) + text.slice(onlyIndex + 1)
  }
  const dropFirstScore = markerPairScore(positions.slice(1))
  const dropLastScore = markerPairScore(positions.slice(0, -1))
  const index = dropFirstScore <= dropLastScore ? positions[0] : positions[positions.length - 1]
  return text.slice(0, index) + text.slice(index + 1)
}

function repairChatMarkdownLine(line) {
  let nextLine = String(line || '')
  nextLine = nextLine.replace(/\*\*\*([^*\n]+?)\*\*/g, '**$1**')
  nextLine = nextLine.replace(/\*\*(?=[^\s*])([^*\n]*?[^\s*])\*(?!\*)/g, '**$1**')
  nextLine = nextLine.replace(/(^|[^\*])\*(?=[^\s*])([^*\n]*?[^\s*])\*\*/g, (_, prefix, content) => `${prefix}**${content}**`)
  nextLine = nextLine.replace(
    /(^|[\s\u3400-\u9fff\u3000-\u303f\uff00-\uffef])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?=$|[\s\u3400-\u9fff\u3000-\u303f\uff00-\uffef])/g,
    (_, prefix, content) => `${prefix}**${content}**`,
  )
  nextLine = nextLine.replace(/(^|(?:\s|[>•\-])\s*)\*([^*\n]{1,40}?[：:])\*(?=\s|$)/g, (_, prefix, content) => `${prefix}**${content}**`)
  nextLine = nextLine.replace(/(^|(?:\s|[>•\-])\s*)\*([^*\n]{1,40}?[：:])(?=\s|$)/g, (_, prefix, content) => `${prefix}**${content}**`)
  nextLine = nextLine.replace(/\*\*([^*\n]*?[\)）\]】》」』”’])\*\*(?=[\u3400-\u9fffA-Za-z0-9])/g, '**$1** ')
  nextLine = removeMostLikelyUnmatchedSingleMarker(nextLine)
  nextLine = removeMostLikelyUnmatchedMarker(nextLine, '**')
  return nextLine
}

function isMarkdownTableSeparatorLine(line) {
  const value = String(line || '').trim()
  if (!value.includes('-')) return false
  return /^\|?[\s:-]+(?:\|[\s:-]+)+\|?$/.test(value)
}

function isMarkdownTableRowLine(line) {
  const value = String(line || '').trim()
  if (!value.includes('|')) return false
  const segments = value.split('|').map((item) => item.trim())
  const meaningfulSegments = segments.filter(Boolean)
  return meaningfulSegments.length >= 2
}

function normalizeMarkdownTables(value) {
  const inputLines = String(value || '').split('\n')
  const outputLines = []
  let index = 0

  while (index < inputLines.length) {
    const currentLine = inputLines[index]
    const nextLine = inputLines[index + 1]
    const isTableHeader = isMarkdownTableRowLine(currentLine) && isMarkdownTableSeparatorLine(nextLine)

    if (!isTableHeader) {
      outputLines.push(currentLine)
      index += 1
      continue
    }

    if (outputLines.length && outputLines[outputLines.length - 1].trim()) {
      outputLines.push('')
    }

    outputLines.push(currentLine.trimEnd())
    index += 1

    while (index < inputLines.length && (isMarkdownTableSeparatorLine(inputLines[index]) || isMarkdownTableRowLine(inputLines[index]))) {
      outputLines.push(String(inputLines[index] || '').trimEnd())
      index += 1
    }

    if (index < inputLines.length && String(inputLines[index] || '').trim()) {
      outputLines.push('')
    }
  }

  return outputLines.join('\n')
}

function stripInlineCitationMarkers(value) {
  return String(value || '')
    .replace(/\[\^\d+\]/g, '')
    .replace(/(?:\[(?:\d{1,3})\]){1,8}/g, '')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
}

export function normalizeChatMarkdown(content) {
  let value = String(content || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  for (let iteration = 0; iteration < 2; iteration += 1) {
    const repaired = value
      .split('\n')
      .map((line) => repairChatMarkdownLine(line))
      .join('\n')
    if (repaired === value) break
    value = repaired
  }
  return stripInlineCitationMarkers(normalizeMarkdownTables(value)).trim()
}
