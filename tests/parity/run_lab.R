# The earlier R version's own numbers on the parity herd, for tests/test_parity.py to compare with the Python port.
#   DAIRY_R=/path/to/r-package OUT=tests/parity Rscript tests/parity/run_lab.R
suppressMessages(pkgload::load_all(Sys.getenv("DAIRY_R"), quiet = TRUE))
out <- Sys.getenv("OUT")
clean <- file.path(tempdir(), "parity-clean")
unlink(clean, recursive = TRUE)
herd <- intake(file.path(out, "herd"), clean, quiet = TRUE)
feed <- load_feed(clean)

num <- function(x) if (is.null(x)) NULL else unname(as.numeric(x))
df <- function(x) {
  if (is.null(x)) return(NULL)
  class(x) <- "data.frame"
  for (a in c("definition", "verdict", "headline", "benchmark", "bands", "cases", "detail", "fit",
              "p_value", "groups", "outcome")) attr(x, a) <- NULL
  x
}

hs <- herd_summary(herd)
pc <- pen_card(herd, 21)
fs_par <- first_service(herd, vwp = 50, by = "parity")
ttp_par <- time_to_pregnancy(herd, by = "parity")
pl_par <- pregnancy_loss(herd, by = "parity")
ci_par <- calving_interval(herd, by = "parity")
afc_yr <- age_first_calving(herd, by = "calving_year")
cb_groups <- c("service", "month", "dim_band", "technician", "sire", "parity")
cb <- lapply(stats::setNames(cb_groups, cb_groups), function(g) {
  r <- conception_by(herd, g)
  list(rows = df(r), p_value = num(attr(r, "p_value")))
})
dp_par <- dry_period_length(herd, by = "parity")
ld <- lactation_data(herd)
rr_met_rp <- risk_ratio(ld, "metritis", "retained_placenta")
rr_met_par <- risk_ratio(ld, "metritis", "parity", exposed = "1")
fde_met <- fresh_disease_effects(herd, "metritis")
fde_rp <- fresh_disease_effects(herd, "retained_placenta")

res <- list(
  as_of = format(herd_as_of(herd)),
  status = as.list(table(cow_status(herd))),
  lactations = nrow(herd$lactations),
  end_reasons = as.list(table(herd$lactations$end_reason)),
  herd = list(median_dim = num(hs$median_dim), tested = hs$test$tested, p10 = num(hs$test$p10),
              p50 = num(hs$test$p50), p90 = num(hs$test$p90), scc_tested = hs$test$scc_tested,
              scc_over_200 = hs$test$scc_over_200, lactation = hs$lactation, repro = hs$repro),
  pens = df(pen_summary(herd)),
  pen21 = list(milk = as.list(pc$milk), health = pc$health),
  incidence = lapply(c(clinical_mastitis = "clinical_mastitis", retained_placenta = "retained_placenta",
                       displaced_abomasum = "displaced_abomasum", milk_fever = "milk_fever", lameness = "lameness"),
                     function(e) if (e %in% herd$events$std_event) df(incidence_risk(herd, e, within_dim = 30, by = "parity")) else NULL),
  pregnancy_rate = df(pregnancy_rate(herd, vwp = 50, by = "parity")),
  pregnancy_rate_cycles = df(pregnancy_rate(herd, vwp = 50, by = "none", cycles = TRUE)),
  pregnant_by_150 = df(pregnant_by(herd, days = 150, by = "parity")),
  first_service = list(rows = df(fs_par), bands = df(attr(fs_par, "bands"))),
  time_to_pregnancy = list(rows = df(ttp_par), p_value = num(attr(ttp_par, "p_value"))),
  pregnancy_loss = list(rows = df(pl_par), cases = nrow(attr(pl_par, "cases"))),
  calving_interval = df(ci_par),
  age_first_calving = df(afc_yr),
  conception_by = cb,
  dry_period_length = list(rows = df(dp_par), n_detail = nrow(attr(dp_par, "detail"))),
  left_reasons_reason = list(
    rows = df(left_reasons(herd, by = "reason")),
    average_herd = attr(left_reasons(herd, by = "reason"), "average_herd"),
    cow_years = attr(left_reasons(herd, by = "reason"), "cow_years"),
    total_left = attr(left_reasons(herd, by = "reason"), "total_left"),
    total_per_100_cow_years = attr(left_reasons(herd, by = "reason"), "total_per_100_cow_years")
  ),
  left_reasons_dim = df(left_reasons(herd, by = "dim_band")),
  left_herd_60 = df(left_herd(herd, within_dim = 60, by = "parity")),
  event_months_metritis = list(
    rows = df(event_months(herd, "metritis", by = "calendar_month")),
    p_value = num(attr(event_months(herd, "metritis", by = "calendar_month"), "p_value"))
  ),
  mastitis_month = df(mastitis_incidence(herd, by = "month", months = 12)),
  mastitis_pooled = as.list(df(mastitis_incidence(herd, by = "none", first_only = TRUE, months = 12))[1, ]),
  lactation_data = list(
    rows = nrow(ld),
    columns = names(ld),
    pregnant = sum(ld$pregnant),
    dry_days_non_na = sum(!is.na(ld$dry_days)),
    first_service_outcome = as.list(table(ld$first_service_outcome, useNA = "ifany")),
    metritis = sum(ld$metritis),
    retained_placenta = sum(ld$retained_placenta),
    displaced_abomasum = sum(ld$displaced_abomasum),
    clinical_mastitis = sum(ld$clinical_mastitis),
    milk_fever = sum(ld$milk_fever)
  ),
  risk_ratio = list(
    metritis_by_rp = as.list(df(rr_met_rp)[1, ]),
    metritis_by_parity = as.list(df(rr_met_par)[1, ])
  ),
  fresh_disease_effects = list(
    metritis = list(milk = df(fde_met$milk), removal = as.list(df(fde_met$removal)[1, ]), days_open = df(fde_met$days_open)),
    retained_placenta = list(milk = df(fde_rp$milk), removal = as.list(df(fde_rp$removal)[1, ]), days_open = df(fde_rp$days_open))
  ),
  scc_screen_parity = df(scc_screen(herd, by = "parity")),
  scc_screen_pen = df(scc_screen(herd, by = "pen")),
  scc_dynamics_parity = df(scc_dynamics(herd, by = "parity")),
  scc_dynamics_all = df(scc_dynamics(herd, by = "none")),
  feed_efficiency = df(feed_efficiency(herd, feed, days = 7)),
  iofc = df(iofc(herd, feed, milk_price = 21, days = 7)),
  loading_ingredient = df(loading_accuracy(feed, by = "ingredient")),
  loading_feeder = df(loading_accuracy(feed, by = "feeder")),
  refusals = df(refusals(feed, days = 7)),
  consistency = df(feeding_consistency(feed, days = 14))
)
jsonlite::write_json(res, file.path(out, "lab_results.json"), auto_unbox = TRUE, digits = 10, pretty = TRUE, na = "null")
cat("wrote", file.path(out, "lab_results.json"), "\n")
