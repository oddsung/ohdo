# Commercial licensing

> **TL;DR** — ohdo's desktop client and core libraries are released under **AGPL-3.0**.
> If AGPL doesn't fit your use case (e.g. you want to redistribute ohdo as part of a closed-source product, or run a hosted service without releasing your modifications), a **separately negotiated commercial license** is available.

## Why AGPL-3.0?

ohdo follows an **open-core** strategy:

- **Desktop client + core libraries (this repo)** — AGPL-3.0. Free to use, modify, redistribute.
- **Hosted SaaS / Pro features (planned, future repo)** — separately licensed (closed source).

AGPL-3.0 was chosen because it:

1. Lets individual developers and companies use ohdo on their own machines for free, with strong assurance that the project remains open.
2. Prevents a third party from forking ohdo, adding a thin SaaS wrapper, and selling it as a closed product without contributing anything back. The AGPL "network use is distribution" clause makes that path legally and practically expensive.
3. Keeps the door open for a sustainable commercial offering by the original copyright holder, since the copyright holder can dual-license under different terms.

You can read the full text in [`LICENSE`](LICENSE).

## When you do NOT need a commercial license

You're fine with AGPL-3.0 if you:

- Use ohdo on your own machine to automate your own workflows.
- Use ohdo internally inside an organization, **as long as you do not modify the source and offer the modified version as a network/web service to third parties**. (Internal use of an unmodified or self-modified copy by employees is fine — AGPL is triggered specifically by *offering* a modified network service.)
- Distribute ohdo (or a modified ohdo) as a desktop application **and ship the corresponding source under AGPL-3.0**.
- Embed ohdo in another AGPL-compatible open-source project.

## When you DO need a commercial license

Reach out for a separately negotiated license if you:

- Want to **redistribute ohdo as part of a closed-source product** (desktop or otherwise) without releasing your application's source under AGPL-3.0.
- Want to **operate a hosted SaaS that uses a modified ohdo** without making your modifications public under AGPL-3.0.
- Want to **bundle ohdo into a proprietary RPA platform** for resale.
- Need an **enterprise indemnification / warranty** clause that AGPL-3.0 does not provide.

The commercial license is intended to be **fair and predictable**: a one-line replacement of "AGPL-3.0" with negotiated terms (typically perpetual + per-deployment or per-seat). It does not change the AGPL-3.0 release for everyone else.

## How to inquire

Open a GitHub issue tagged `commercial-license`, or contact the maintainer using the address in [`pyproject.toml`](pyproject.toml). Include:

1. **Who you are** — company / individual.
2. **What you intend to do** — embed in a product, host as SaaS, OEM resell, etc.
3. **Scale** — approximate number of seats / deployments / end users.
4. **Timeline** — when you'd like to start.

A short call usually clarifies everything within a week.

## Note on contributions

If you want to contribute code that may eventually flow into the commercially-licensed branch, please read [`CONTRIBUTING.md`](CONTRIBUTING.md) — contributors sign off on the [Developer Certificate of Origin (DCO)](https://developercertificate.org/). For larger contributions we may ask for a per-contribution Contributor License Agreement (CLA) so the project can dual-license cleanly. We try to keep this lightweight; the goal is to protect both contributors and the long-term sustainability of the project.
