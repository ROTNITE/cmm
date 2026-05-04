from Lib.orchestrator import run_cmm


def main():
    user_query = input("Пожалуйста, введите ваш запрос: ")
    result = run_cmm(user_query)

    print(f"\n✅ Финальный ответ: {result['final_answer']}")

    trace = result.get("trace_report", {})
    roles_count = len(trace.get("roles_used", []))
    revision_count = trace.get("revision_count", 0)
    warnings = trace.get("warnings", [])

    print(f"\n🧭 Trace summary: roles={roles_count}, revisions={revision_count}")
    if warnings:
        print("⚠️ Warnings:")
        for warning in warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
