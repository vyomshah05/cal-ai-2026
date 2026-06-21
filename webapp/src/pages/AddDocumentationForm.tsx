import { useState, type FormEvent } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input, Label, Textarea } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { TagInput } from '../components/ui/TagInput';
import { submitLibrary } from '../lib/api';
import type { Ecosystem, FunctionIn, LibraryIngestRequest, Tier } from '../types/ingestion';

const ECOSYSTEMS: Ecosystem[] = ['pypi', 'npm', 'cargo', 'go', 'maven', 'rubygems'];
const TIERS: Tier[] = ['niche', 'popular'];

function emptyFunction(): FunctionIn {
  return { qualified_name: '', kind: 'function', signature: '', summary: '', description: '', returns: '', source_url: '' };
}

export function AddDocumentationForm() {
  const [ecosystem, setEcosystem] = useState<Ecosystem>('pypi');
  const [name, setName] = useState('');
  const [version, setVersion] = useState('');
  const [summary, setSummary] = useState('');
  const [homepage, setHomepage] = useState('');
  const [docsUrl, setDocsUrl] = useState('');
  const [tier, setTier] = useState<Tier>('niche');
  const [tags, setTags] = useState<string[]>([]);
  const [functions, setFunctions] = useState<FunctionIn[]>([]);

  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle');
  const [resultMsg, setResultMsg] = useState('');

  function updateFunction(i: number, patch: Partial<FunctionIn>) {
    setFunctions((fns) => fns.map((f, idx) => (idx === i ? { ...f, ...patch } : f)));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus('submitting');
    setResultMsg('');

    const payload: LibraryIngestRequest = {
      ecosystem,
      name,
      version: version || undefined,
      summary: summary || undefined,
      homepage: homepage || undefined,
      docs_url: docsUrl || undefined,
      tier,
      tags,
      functions: functions
        .filter((f) => f.qualified_name.trim())
        .map((f) => ({ ...f, params: null })),
    };

    try {
      const res = await submitLibrary(payload);
      setStatus('success');
      setResultMsg(
        `Added ${res.library_id} → ${res.function_table} (${res.functions_upserted} functions, ${res.tags_upserted} tags).`,
      );
    } catch (err) {
      setStatus('error');
      setResultMsg(err instanceof Error ? err.message : 'Submission failed.');
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Add your documentation</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600 dark:text-slate-400">
          Submits straight into the Supabase corpus Lockstep already serves from, same{' '}
          <code className="rounded bg-black/5 dark:bg-white/10 px-1.5 py-0.5">libraries</code> /{' '}
          <code className="rounded bg-black/5 dark:bg-white/10 px-1.5 py-0.5">fn_*</code> tables the
          scraper pipeline writes to.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card className="p-6 space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Library
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label>Ecosystem</Label>
              <Select value={ecosystem} onChange={(e) => setEcosystem(e.target.value as Ecosystem)}>
                {ECOSYSTEMS.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label>Name</Label>
              <Input required value={name} onChange={(e) => setName(e.target.value)} placeholder="requests" />
            </div>
            <div>
              <Label>Version</Label>
              <Input value={version} onChange={(e) => setVersion(e.target.value)} placeholder="2.34.2" />
            </div>
            <div>
              <Label>Tier</Label>
              <Select value={tier} onChange={(e) => setTier(e.target.value as Tier)}>
                {TIERS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label>Homepage</Label>
              <Input value={homepage} onChange={(e) => setHomepage(e.target.value)} placeholder="https://..." />
            </div>
            <div>
              <Label>Docs URL</Label>
              <Input value={docsUrl} onChange={(e) => setDocsUrl(e.target.value)} placeholder="https://..." />
            </div>
          </div>
          <div>
            <Label>Summary</Label>
            <Textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="One or two sentences describing the library." />
          </div>
          <div>
            <Label>Tags</Label>
            <TagInput tags={tags} onChange={setTags} placeholder="http, async, networking..." />
          </div>
        </Card>

        <Card className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Functions
            </h2>
            <Button type="button" variant="secondary" onClick={() => setFunctions((f) => [...f, emptyFunction()])}>
              + Add function
            </Button>
          </div>

          {functions.length === 0 && (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Optional. Add the key functions you want Lockstep to be able to surface in docs lookups.
            </p>
          )}

          <div className="space-y-4">
            {functions.map((fn, i) => (
              <div key={i} className="rounded-xl border border-black/5 dark:border-white/10 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Function {i + 1}</span>
                  <button
                    type="button"
                    onClick={() => setFunctions((fns) => fns.filter((_, idx) => idx !== i))}
                    className="text-xs text-slate-500 hover:text-red-500"
                  >
                    Remove
                  </button>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <Label>Qualified name</Label>
                    <Input
                      required
                      value={fn.qualified_name}
                      onChange={(e) => updateFunction(i, { qualified_name: e.target.value })}
                      placeholder="requests.get"
                    />
                  </div>
                  <div>
                    <Label>Kind</Label>
                    <Select value={fn.kind} onChange={(e) => updateFunction(i, { kind: e.target.value })}>
                      <option value="function">function</option>
                      <option value="class">class</option>
                      <option value="method">method</option>
                    </Select>
                  </div>
                  <div className="sm:col-span-2">
                    <Label>Signature</Label>
                    <Input
                      value={fn.signature}
                      onChange={(e) => updateFunction(i, { signature: e.target.value })}
                      placeholder="url, params=None, **kwargs"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <Label>Summary</Label>
                    <Input
                      value={fn.summary}
                      onChange={(e) => updateFunction(i, { summary: e.target.value })}
                      placeholder="Sends a GET request."
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <Label>Description</Label>
                    <Textarea
                      rows={2}
                      value={fn.description}
                      onChange={(e) => updateFunction(i, { description: e.target.value })}
                    />
                  </div>
                  <div>
                    <Label>Returns</Label>
                    <Input value={fn.returns} onChange={(e) => updateFunction(i, { returns: e.target.value })} />
                  </div>
                  <div>
                    <Label>Source URL</Label>
                    <Input
                      value={fn.source_url}
                      onChange={(e) => updateFunction(i, { source_url: e.target.value })}
                      placeholder="https://docs.../#requests.get"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={status === 'submitting'}>
            {status === 'submitting' ? 'Submitting…' : 'Submit to Lockstep'}
          </Button>
          {status === 'success' && (
            <p className="text-sm text-teal dark:text-teal-dark">{resultMsg}</p>
          )}
          {status === 'error' && <p className="text-sm text-red-500">{resultMsg}</p>}
        </div>
      </form>
    </div>
  );
}
