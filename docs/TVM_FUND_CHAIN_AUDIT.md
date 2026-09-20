# TVM Ventures VIII / Innovation II fund-chain audit

Audit date: 2026-09-20.

## Question

Investment Canada names **TVM Life Science Ventures VIII SCSp** as the foreign investor for the March 2019 Ocellaris Pharma Inc. and April 2019 Acanthas Pharma Inc. new-business notifications. TVM's current portfolio material attributes those companies to **TVM Life Science Innovation II SCSp**.

The modeling question is whether those names can be treated as the same legal fund, a documented successor/name change, or only a related economic commitment.

## Finding

**Cross-name economic-fund/LP-commitment evidence is supported. Legal-entity equivalence is not established.**

AtlanticBridge therefore does **not** create `SAME_LEGAL_ENTITY_AS` between TVM Life Science Ventures VIII SCSp and TVM Life Science Innovation II SCSp, does not infer a formal rename, and does not promote either Canadian outcome into the training set.

## Evidence chain

1. **SEC Form D — 2019-02-08.** TVM Life Science Ventures VIII SCSp is identified as a Luxembourg limited partnership formed in 2018, CIK 0001767198. TVM Life Science Ventures VIII (GP) S.a.r.l. is identified as its general partner.

   Source: https://www.sec.gov/Archives/edgar/data/1767198/000176719819000001/xslFormDX01/primary_doc.xml

2. **Investment Canada — 2019-03 / 2019-04.** The federal notification index names TVM Life Science Ventures VIII SCSp for Ocellaris Pharma Inc. and Acanthas Pharma Inc.

   Source: https://ised-isde.canada.ca/site/investment-canada-act/en/search/decisions-and-notification-index/t?page=7

3. **Bukwang 2019 Q2 investor material.** In a deck covering 2019-04-01 through 2019-06-30, Bukwang says it participates as a limited partner in TVM Life Science Innovation II. This places the Innovation II name in contemporaneous use during the same period as the Canadian notifications.

   Source: https://www.bukwang.co.kr/board/download_pdf.php?bo_table=ir&board=Y&file_name=b_file_1692755732i1pm737gka.pdf&o_file_name=2019%EB%85%84+2%EB%B6%84%EA%B8%B0.pdf

4. **Bukwang filed annual report — 2023-03-20.** The investment table labels Bukwang's holding **TVM Life Science Innovation II**. The corresponding footnote states that Bukwang entered its limited-partner investment contract in the TVM Capital-managed **TVM Life Science Ventures VIII**. This is direct company-controlled evidence that the same Bukwang fund commitment is described under both names.

   Source: https://www.bukwang.co.kr/board/download_pdf.php?bo_table=announce&board=Y&file_name=b_file_16902485857eppsv9z7c.pdf&o_file_name=%5B%EB%B6%80%EA%B4%91%EC%95%BD%ED%92%88%5D%EC%82%AC%EC%97%85%EB%B3%B4%EA%B3%A0%EC%84%9C%282023.03.20%29.pdf

5. **Minnesota Life 2019 Q3 statement.** The insurer reports an investment named **TVM Life Science Innovation II, SCSp** and identifies **TVM Life Science Ventures VIII (GP), S.a.r.l.** in the adjacent manager/general-partner field. This independently corroborates the cross-name administrative relationship in 2019, but it is not a Luxembourg legal-name-change record.

   Source: https://www.securian.com/content/dam/doc/sf/mn-life-2019-3q-statement.pdf

6. **SEC Schedule 13D — 2020-01-14.** A later SEC filing identifies **TVM Life Science Innovation II SCSp** as a Luxembourg special limited partnership and **TVM Life Science Innovation II (GP) S.a r.l.** as its general partner. The filing treats those as explicit legal names.

   Source: https://www.sec.gov/Archives/edgar/data/1757097/000119312520007168/d869674dsc13d.htm

7. **Portfolio relationship.** TVM's Ocellaris page says Ocellaris is fully financed by TVM Life Science Innovation II SCSp. TVM material also places Acanthas under the Innovation II strategy.

   Ocellaris: https://tvm-capital.com/portfolio/ocellaris-pharma/

## Interpretation boundary

The combined evidence supports this narrow statement:

> An LP commitment and fund activity associated with the 2019 Ventures VIII name is also reported under the Innovation II name, and Innovation II is the TVM fund tied to the Ocellaris/Acanthas portfolio activity.

It does **not** yet support any of the following:

- that Ventures VIII SCSp and Innovation II SCSp are the same Luxembourg legal entity;
- that one legal entity formally changed its registered name to the other;
- the effective date of any such name change;
- that every obligation or portfolio interest of Ventures VIII transferred to Innovation II;
- a first Canadian operating date for Ocellaris or Acanthas.

An authoritative Luxembourg register/name-history filing is required before AtlanticBridge records a legal alias or formal succession.

## Modeling disposition

Both Canadian cases remain:

- `outcome_classification = UNRESOLVED`;
- `first_canadian_operations_date = null`;
- `model_eligible = false`.

This is deliberate. Cross-name fund evidence improves provenance but does not establish the operating outcome date or historical feature availability needed for a first-entry backtest.
