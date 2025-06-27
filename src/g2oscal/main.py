all_blobs = list(storage_client.list_blobs(BUCKET_NAME, prefix=SOURCE_PREFIX))
files_to_process = [blob for blob in all_blobs if blob.name.lower().endswith('.pdf')]
if not files_to_process: logging.warning(f"No PDF files found in gs://{BUCKET_NAME}/{SOURCE_PREFIX}. Exiting."); return

if TEST_MODE: 
    files_to_process = files_to_process[:3]
    logging.warning(f"--- TEST MODE: Processing a maximum of {len(files_to_process)} files. ---")

semaphore = asyncio.Semaphore(CONCURRENT_REQUEST_LIMIT)
tasks = [process_baustein_pdf(blob, semaphore) for blob in files_to_process]

all_results = await asyncio.gather(*tasks)
successful_results = [res for res in all_results if res and res[0] and res[1]]

final_catalog = merge_results(successful_results, base_catalog)

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
output_filename = f"{FINAL_RESULT_PREFIX}MERGED_BSI_Catalog_{timestamp}.json"
output_blob = bucket.blob(output_filename)
output_blob.upload_from_string(json.dumps(final_catalog, indent=2, ensure_ascii=False), "application/json")

logging.info("--- Batch Job Summary ---")
logging.info(f"Successfully processed: {len(successful_results)} file(s).")
logging.info(f"Failed to process: {len(files_to_process) - len(successful_results)} file(s).")
logging.info(f"Final merged catalog uploaded to: gs://{BUCKET_NAME}/{output_filename}")

if __name__ == "__main__":
    asyncio.run(main())