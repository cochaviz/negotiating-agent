import json
import sys

def run(number_of_runs=10) -> list[dict]:
    all_results = []

    for _ in range(number_of_runs):
        exec(open("run.py").read())

        with open("results/results_summary.json", "r") as f:
            results = json.loads(f.read())
            all_results.append(results)

    return all_results

def average_of(results: list[dict], target_metric: str|None) -> float:
    if target_metric is None:
        raise ValueError

    social_welfare = list(map((lambda m: float(m[target_metric])), results))
    return sum(social_welfare)/len(social_welfare)

def average_social_welfare(results: list[dict]):
    return average_of(results, target_metric="social_welfare")


if __name__=="__main__":
    try:
        results = run(int(sys.argv[1]))
    except:
        results = run()

    print("Average social welfare:", average_social_welfare(results))
