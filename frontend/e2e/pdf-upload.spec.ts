import { test, expect } from './fixtures'

const auth = (token: string) => ({ Authorization: `Bearer ${token}` })

/** A minimal one-page PDF showing `lines` (valid xref, so PDF readers accept it). */
function makePdf(lines: string[]): Buffer {
  const escape = (s: string) => s.replace(/[\\()]/g, (c) => `\\${c}`)
  const stream = ['BT', '/F1 10 Tf', '50 780 Td', '14 TL', ...lines.map((l) => `(${escape(l)}) '`), 'ET'].join('\n')
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ]
  let body = '%PDF-1.4\n'
  const offsets: number[] = []
  objects.forEach((obj, i) => {
    offsets.push(Buffer.byteLength(body))
    body += `${i + 1} 0 obj\n${obj}\nendobj\n`
  })
  const xref = Buffer.byteLength(body)
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  body += offsets.map((o) => `${String(o).padStart(10, '0')} 00000 n \n`).join('')
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(body, 'latin1')
}

function ris(entries: { title: string; doi: string; author: string; year: number }[]): string {
  return entries
    .map((e) =>
      ['TY  - JOUR', `TI  - ${e.title}`, `AU  - ${e.author}`, `PY  - ${e.year}`, `DO  - ${e.doi}`, 'ER  - ', ''].join('\n'),
    )
    .join('\n')
}

test.describe('Bulk PDF upload', () => {
  test('matches PDFs by DOI and title, then attaches the confirmed ones', async ({
    pageHelper,
    api,
    testUser,
    page,
    request,
  }) => {
    const id = Math.random().toString(36).slice(2, 8)
    const byTitle = { title: `Parenting stress and child anxiety in cohort ${id}`, doi: `10.5555/title-${id}`, author: 'Smith, John', year: 2020 }
    const byDoi = { title: `Mindfulness for parents trial ${id}`, doi: `10.5555/doi-${id}`, author: 'Jansen, Jan', year: 2019 }

    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)
    await api.uploadRisFile(testUser.token, project.id, ris([byTitle, byDoi]))

    await page.goto(`/projects/${project.id}/articles`)
    await page.getByTestId('upload-pdfs-link').click()
    await expect(page).toHaveURL(new RegExp(`/projects/${project.id}/articles/upload-pdfs$`))

    await page.getByTestId('pdf-file-input').setInputFiles([
      { name: 'paper.pdf', mimeType: 'application/pdf', buffer: makePdf(['Journal of Tests', byTitle.title, 'John Smith 2020']) },
      { name: `${byDoi.doi.replace('/', '_')}.pdf`, mimeType: 'application/pdf', buffer: makePdf(['Body text']) },
      { name: 'unrelated.pdf', mimeType: 'application/pdf', buffer: makePdf(['Something else entirely']) },
      { name: 'notes.pdf', mimeType: 'application/pdf', buffer: Buffer.from('not a pdf') },
    ])

    const rows = page.getByTestId('pdf-row')
    await expect(rows).toHaveCount(4)
    await expect(rows.nth(0)).toContainText(byTitle.title)
    await expect(rows.nth(0)).toContainText('Matched')
    await expect(rows.nth(1)).toContainText(byDoi.title)
    await expect(rows.nth(1)).toContainText('DOI in file name')
    await expect(rows.nth(2)).toContainText('No match')
    await expect(rows.nth(3)).toContainText('Rejected')

    await page.getByTestId('pdf-confirm').click()
    await expect(rows.nth(0)).toContainText('Attached')
    await expect(rows.nth(1)).toContainText('Attached')

    const res = await request.get(`/api/v1/projects/${project.id}/articles?has_full_text=true`, {
      headers: auth(testUser.token),
    })
    const titles = (await res.json()).data.map((a: { title: string }) => a.title).sort()
    expect(titles).toEqual([byTitle.title, byDoi.title].sort())
  })
})
