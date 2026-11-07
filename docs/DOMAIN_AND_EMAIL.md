# Domain and company email for VIVID

Researched 7 November 2026. Prices change, so check them again before you pay. Nothing has been bought and no accounts have been created.

## Recommendation in one line

Buy **vividreminders.com** at **Cloudflare** (about **US$11 a year**). Use **Zoho Mail's free plan** for **hello@vividreminders.com** (GHS 0). Point the domain at Render, which is free on your plan. Total: about **US$11 a year**. Add **vividreminders.com.gh** later if you want a Ghana address. It costs much more.

## 1. The domain (your web address)

| Option | Price per year | Notes |
|---|---|---|
| **vividreminders.com** (recommended) | **≈ US$11** at Cloudflare (sold at cost, and renewals cost the same). About GHS 220 first year at Truehost Ghana, GHS 230 to renew. | Matches the product name "Vivid Reminders". Easy to say and spell. It did not appear in DNS on 7 Nov 2026, which suggests it is free to buy. Confirm at checkout. |
| vividreminders.com.gh / vivid.com.gh | Roughly **GHS 250–700** at Ghanaian registrars. Foreign registrars charge more than US$100. | Says "Ghana" clearly. The **.com.gh** registry usually asks for business registration documents (Registrar-General certificate). It is slower and more expensive. Neither name appeared in DNS. |
| vividreminder.com, vividgh.com | ≈ US$11 | Fallbacks if the first choice is taken. |

Why Cloudflare: it charges no markup and no "first-year discount then a big renewal". It also gives free DNS, which makes connecting Render easy. Pay by card. If you'd rather pay in cedis with mobile money, **Truehost Ghana** (gh.truehost.com) sells .com for about GHS 220.

Avoid plain **vivid.com**. It is an established premium name, and buying it would cost thousands of dollars if it is for sale at all.

## 2. Company email (e.g. hello@vividreminders.com)

| Option | Price | Good for |
|---|---|---|
| **Zoho Mail – Forever Free** (recommended to start) | **Free**: up to 5 mailboxes, 5 GB each, one domain | Starting out. You read it on the web or in the Zoho Mail phone app. It can't connect to Gmail/Outlook apps (no IMAP). Make sure you pick the **Free** plan at sign-up, because Zoho shows paid plans first. |
| Zoho Mail Lite | ≈ **US$1 per mailbox per month** (paid yearly) | The next step up if you want it inside other mail apps. |
| Google Workspace Business Starter | ≈ **US$7 per mailbox per month** yearly (≈ US$8.40 month-to-month) | Gmail look and feel, plus Google Drive and Meet. Choose this if you already live in Gmail. |
| Microsoft 365 Business Basic | ≈ **US$7 per mailbox per month** yearly (price rose from US$6 on 1 July 2026) | Outlook, Teams and OneDrive. |

My pick: start with **Zoho Free** and one address, **hello@vividreminders.com**. Add aliases such as support@ and privacy@ that all land in the same inbox. Move to Google Workspace only when you hire people.

When it works, add `CONTACT_EMAIL=hello@vividreminders.com` on Render (Environment). The privacy, terms and data-deletion pages will then show it. Meta also likes to see a company email.

## 3. Pointing the domain at VIVID on Render (free)

1. Render → the VIVID service → **Settings → Custom Domains → + Add Custom Domain**. Enter `vividreminders.com` and save. Render adds `www.vividreminders.com` automatically and redirects it.
2. At Cloudflare (or your registrar's DNS page), add:
   - **Root:** a `CNAME` for `@` → `vivid-bot.onrender.com`. Cloudflare allows this through "CNAME flattening". At other registrars, use an `A` record for `@` → `216.24.57.1`.
   - **www:** `CNAME` `www` → `vivid-bot.onrender.com`
   - Delete any `AAAA` records for the domain.
   - At Cloudflare, set these records to **DNS only** (grey cloud) so Render can issue the certificate.
3. Back in Render, click **Verify**. Render creates the HTTPS certificate itself.
4. On Render, set `PUBLIC_BASE_URL=https://vividreminders.com` and redeploy.
5. Update the website addresses in the Meta app (Privacy policy URL, Terms URL, Data deletion URL) to the new domain. Update the Paystack callback too, if you set one by hand. Keep the old `onrender.com` address working, because the WhatsApp webhook can stay on it.

Your Render plan includes custom domains at no extra cost (2 on Hobby, 15 on Pro; each extra one is US$0.25 a month).

Zoho's setup wizard gives you **MX**, **SPF** (TXT) and **DKIM** (TXT) records to add in the same DNS page. They don't clash with the Render records.

## Sources
- Render custom domains: https://render.com/docs/custom-domains and https://render.com/docs/configure-other-dns
- Cloudflare .com at-cost price and the 1 Nov 2026 Verisign increase: https://costgoat.com/pricing/cloudflare-domains
- Truehost Ghana .com price: https://gh.truehost.com/domain-renewal-vs-registration-price-ghana/
- .com.gh price ranges: https://blog.faciotech.com/complete-guide-com-gh-domains-ghana and https://domainoffer.net/tld/com.gh/atakdomain
- Zoho Mail plans: https://www.zoho.com/mail/zohomail-pricing.html
- Google Workspace pricing: https://www.emailvendorselection.com/google-workspace-pricing/
- Microsoft 365 Business Basic 2026 price: https://office-watch.com/2026/microsoft-365-business-price-increase-2026/
