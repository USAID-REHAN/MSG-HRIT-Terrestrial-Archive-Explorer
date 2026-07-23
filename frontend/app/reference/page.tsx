"use client";

import { useEffect, useState } from "react";
import { ExplainBlock } from "@/components/ui/ExplainBlock";
import { GlassPanel } from "@/components/ui/GlassPanel";
import { productDomainExample } from "@/lib/product-domain-examples";
import { api, ProductReference } from "@/lib/api-client";

export default function ReferencePage() {
  const [rows, setRows] = useState<ProductReference[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .reference()
      .then(setRows)
      .catch((e) => setError(e.message));
  }, []);

  const channels = rows.filter((r) => r.product_kind === "channel");
  const composites = rows.filter((r) => r.product_kind === "composite");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-fg-heading">
          About the data
        </h1>
        <p className="mt-1 text-fg-muted">
          Glossary of SEVIRI channels, composites, and terms used in this app
        </p>
      </div>

      <ExplainBlock title="Quick glossary">
        <p>
          <strong className="text-fg-heading">MSG-2</strong> — Meteosat Second
          Generation satellite series providing continuous Earth observation from
          geostationary orbit. SEVIRI is its main imager.
        </p>
        <p>
          <strong className="text-fg-heading">SEVIRI</strong> — Spinning Enhanced
          Visible and Infrared Imager: twelve spectral channels including high-
          resolution visible (HRV), solar/near-IR, water vapour, and thermal IR.
        </p>
        <p>
          <strong className="text-fg-heading">IODC disk</strong> — Indian Ocean Data
          Coverage view: the geostationary disk geometry commonly used for South
          Asia / Indian Ocean monitoring (as opposed to the 0° European disk).
        </p>
        <p>
          <strong className="text-fg-heading">Terminator / twilight</strong> — the
          moving day/night boundary on Earth. Near that boundary, solar channels
          can be only partially populated — exactly why this tool samples a
          twilight timeslot each day.
        </p>
        <p>
          <strong className="text-fg-heading">Composite (RGB)</strong> — a colour
          image built by assigning specific channels or channel differences to
          red/green/blue so phenomena (dust, ash, airmass, convection) pop for
          human interpretation.
        </p>
      </ExplainBlock>

      {error ? (
        <GlassPanel className="border-rose-400/40">
          <p className="text-sm text-rose-700 theme-dark:text-rose-100">{error}</p>
        </GlassPanel>
      ) : null}

      <ProductGroup title="Twelve SEVIRI channels" items={channels} />
      <ProductGroup title="Public SEVIRI composites (100)" items={composites} />
    </div>
  );
}

function ProductGroup({
  title,
  items,
}: {
  title: string;
  items: ProductReference[];
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-accent-soft">{title}</h2>
      <div className="space-y-3">
        {items.map((r) => (
          <GlassPanel key={r.product_name} padding="md">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-lg font-semibold text-fg-heading">
                {r.product_name}
              </h3>
              <span className="text-xs text-fg-subtle">
                {r.wavelength_or_spectral_band} · {r.approximate_resolution}
              </span>
            </div>
            <p className="mt-3 text-[15px] leading-relaxed text-fg">
              {r.plain_language_description}
            </p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              <Mini
                title="Agriculture"
                text={r.agriculture_application}
                example={productDomainExample(r.product_name, "agriculture")}
              />
              <Mini
                title="Aviation"
                text={r.aviation_application}
                example={productDomainExample(r.product_name, "aviation")}
              />
              <Mini
                title="Natural resources"
                text={r.natural_resource_application}
                example={productDomainExample(
                  r.product_name,
                  "natural_resources"
                )}
              />
              <Mini
                title="Disaster response"
                text={r.disaster_response_application}
                example={productDomainExample(
                  r.product_name,
                  "disaster_response"
                )}
              />
            </div>
          </GlassPanel>
        ))}
      </div>
    </section>
  );
}

function Mini({
  title,
  text,
  example,
}: {
  title: string;
  text: string;
  example: string;
}) {
  return (
    <div className="rounded-xl border border-glass-border bg-surface-panel p-3 text-sm text-fg-soft">
      <div className="text-[11px] uppercase tracking-[0.14em] text-accent/80">
        {title}
      </div>
      <p className="mt-1">{text}</p>
      <p className="mt-2 border-t border-glass-border pt-2 text-fg-muted">
        {example}
      </p>
    </div>
  );
}
