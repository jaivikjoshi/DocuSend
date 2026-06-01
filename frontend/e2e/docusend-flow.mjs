import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const APP_URL = process.env.E2E_APP_URL ?? 'http://127.0.0.1:5173';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const USER_ID = '00000000-0000-4000-8000-000000000001';
const DOC_ID = '11111111-1111-4111-8111-111111111111';

const user = {
  id: USER_ID,
  aud: 'authenticated',
  role: 'authenticated',
  email: 'jaivikjoshi7@gmail.com',
  user_metadata: { full_name: 'Jaivik Joshi' },
};

let documentRow = null;
let lineItems = [];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function json(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
    headers: {
      'access-control-allow-origin': '*',
      'access-control-allow-headers': '*',
      'access-control-allow-methods': '*',
    },
  });
}

function parseBody(request) {
  const raw = request.postData();
  return raw ? JSON.parse(raw) : {};
}

function matchesObjectAccept(request) {
  return request.headers().accept?.includes('application/vnd.pgrst.object+json');
}

async function installMocks(page) {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({
    status: 200,
    contentType: 'text/css',
    body: '',
  }));
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ status: 204 }));

  await page.route('**/auth/v1/token**', route => json(route, {
    access_token: 'test-access-token',
    token_type: 'bearer',
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    refresh_token: 'test-refresh-token',
    user,
  }));

  await page.route('**/auth/v1/user**', route => json(route, user));

  await page.route('**/storage/v1/object/documents/**', route => {
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204 });
    return json(route, { Key: route.request().url().split('/object/documents/')[1] });
  });

  await page.route('**/rest/v1/documents**', route => {
    const request = route.request();
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204 });
    const url = new URL(request.url());
    const wantsSingle = matchesObjectAccept(request);

    if (request.method() === 'GET') {
      if (url.searchParams.get('id') === `eq.${DOC_ID}`) {
        return json(route, { ...documentRow, line_items: lineItems });
      }
      return json(route, documentRow ? [{ ...documentRow, line_items: lineItems }] : []);
    }

    if (request.method() === 'POST') {
      const body = parseBody(request);
      documentRow = {
        id: DOC_ID,
        user_id: USER_ID,
        file_name: body.file_name,
        file_size: body.file_size,
        status: body.status,
        document_type: 'unknown',
        vendor: null,
        document_date: null,
        total: null,
        tax: null,
        confidence: null,
        warnings: [],
        source_mode: 'regex',
        storage_path: null,
        line_items: [],
      };
      return json(route, wantsSingle ? documentRow : [documentRow], 201);
    }

    if (request.method() === 'PATCH') {
      const body = parseBody(request);
      documentRow = { ...documentRow, ...body };
      return json(route, wantsSingle ? documentRow : [documentRow]);
    }

    if (request.method() === 'DELETE') {
      documentRow = null;
      lineItems = [];
      return json(route, []);
    }

    return route.continue();
  });

  await page.route('**/rest/v1/line_items**', route => {
    const request = route.request();
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204 });
    if (request.method() === 'DELETE') {
      lineItems = [];
      return json(route, []);
    }
    if (request.method() === 'POST') {
      const body = parseBody(request);
      lineItems = Array.isArray(body) ? body : [body];
      return json(route, lineItems, 201);
    }
    return json(route, lineItems);
  });

  await page.route('http://localhost:8000/api/process_async', route => {
    documentRow = {
      ...documentRow,
      status: 'processed',
      document_type: 'invoice',
      vendor: 'Acme Supplies',
      document_date: '2026-05-29',
      total: 42.50,
      tax: 3.50,
      confidence: 93,
      source_mode: 'regex',
    };
    lineItems = [{
      document_id: DOC_ID,
      user_id: USER_ID,
      description: 'Paper',
      quantity: 2,
      unit_price: 19.5,
      total: 39,
      confidence: 91,
      row_index: 0,
    }];
    return json(route, { message: 'Accepted', document_id: DOC_ID, status: 'processing' }, 202);
  });

  await page.route('http://localhost:8000/api/export', route => {
    const body = parseBody(route.request());
    assert(body.document_ids?.[0] === DOC_ID, 'Export must request authenticated document IDs.');
    return route.fulfill({
      status: 200,
      contentType: 'application/zip',
      body: 'fake-zip',
      headers: {
        'content-disposition': 'attachment; filename="docusend-export.zip"',
        'access-control-allow-origin': '*',
        'access-control-expose-headers': 'Content-Disposition',
      },
    });
  });
}

async function waitForServer(url, child) {
  const started = Date.now();
  while (Date.now() - started < 90000) {
    if (child.exitCode !== null) throw new Error('Vite dev server exited early.');
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function main() {
  const tmp = await mkdtemp(path.join(tmpdir(), 'docusend-e2e-'));
  const samplePath = path.join(tmp, 'sample_invoice.pdf');
  await writeFile(samplePath, '%PDF-1.4\n% DocuSend E2E sample\n%%EOF\n');

  const server = spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173'], {
    cwd: path.resolve(__dirname, '..'),
    stdio: 'inherit',
    env: { ...process.env },
  });

  let browser;
  try {
    await waitForServer(APP_URL, server);
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ acceptDownloads: true });
    page.on('pageerror', error => console.error('PAGE_ERROR:', error.message));
    page.on('requestfailed', request => console.error('REQUEST_FAILED:', request.url(), request.failure()?.errorText));
    await installMocks(page);

    await page.goto(APP_URL, { waitUntil: 'commit' });
    try {
      await page.getByLabel('Email Address').fill(user.email);
    } catch (error) {
      console.error(await page.content());
      throw error;
    }
    await page.getByLabel('Password').fill('123456');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.getByRole('heading', { name: 'Dashboard' }).waitFor();

    await page.locator('#file-input').setInputFiles(samplePath);
    await page.getByText('Parsing in Background').waitFor();
    await page.getByText('Done').waitFor({ timeout: 10000 });
    await page.getByText('Acme Supplies').waitFor();
    await page.getByText('Processed', { exact: true }).waitFor();

    await page.getByRole('row', { name: /sample_invoice.pdf/i }).click();
    await page.getByRole('button', { name: /edit/i }).click();
    await page.locator('input.form-input').first().fill('Edited Vendor');
    await page.getByRole('button', { name: /save/i }).click();
    await page.getByText('Edited Vendor').waitFor();

    await page.locator('#nav-export').click();
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#btn-export-csv').click();
    const download = await downloadPromise;
    assert((await download.suggestedFilename()) === 'docusend-export.zip', 'CSV export should download a ZIP.');

    await page.locator('#nav-documents').click();
    await page.getByRole('row', { name: /sample_invoice.pdf/i }).click();
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: /delete/i }).click();
    await page.getByText('Edited Vendor').waitFor({ state: 'hidden' });

    await page.locator('#btn-logout').click();
    await page.getByRole('heading', { name: /welcome back/i }).waitFor();
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
    await rm(tmp, { recursive: true, force: true });
  }
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
