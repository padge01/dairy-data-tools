# The earlier R version's own numbers on the parity herd, for tests/test_parity.py to compare with the Python port.
#   OUT=tests/parity Rscript tests/parity/run_lab.R
suppressMessages(pkgload::load_all(Sys.getenv("DAIRY_R"), quiet = TRUE))
out <- Sys.getenv("OUT")
clean <- file.path(tempdir(), "parity-clean")
unlink(clean, recursive = TRUE)
herd <- intake(file.path(out, "herd"), clean, quiet = TRUE)
feed <- load_feed(clean)

num <- function(x) if (is.null(x)) NULL else unname(as.numeric(x))
df <- function(x) { class(x) <- "data.frame"; attributes(x)[c("definition", "verdict", "headline")] <- NULL; x }

hs <- herd_summary(herd)
pc <- pen_card(herd, 21)
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
  feed_efficiency = df(feed_efficiency(herd, feed, days = 7)),
  iofc = df(iofc(herd, feed, milk_price = 21, days = 7)),
  loading_ingredient = df(loading_accuracy(feed, by = "ingredient")),
  loading_feeder = df(loading_accuracy(feed, by = "feeder")),
  refusals = df(refusals(feed, days = 7)),
  consistency = df(feeding_consistency(feed, days = 14))
)
jsonlite::write_json(res, file.path(out, "lab_results.json"), auto_unbox = TRUE, digits = 10, pretty = TRUE, na = "null")
cat("wrote", file.path(out, "lab_results.json"), "\n")
