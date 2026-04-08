def smart_fill(page, profile, answers, cover_letter):
    inputs = page.locator("input, textarea").all()

    for field in inputs:
        try:
            name = field.get_attribute("name") or ""

            if "name" in name.lower():
                field.fill(profile["first_name"])

            elif "email" in name.lower():
                field.fill(profile["email"])

            elif "phone" in name.lower():
                field.fill(profile["phone"])

        except:
            continue

    # Textareas → cover letter / answers
    textareas = page.locator("textarea").all()

    for t in textareas:
        try:
            t.fill(cover_letter[:500])
        except:
            pass

    # Upload resume
    try:
        page.set_input_files("input[type='file']", "resume.pdf")
    except:
        pass