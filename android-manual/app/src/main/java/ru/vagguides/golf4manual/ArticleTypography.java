package ru.vagguides.golf4manual;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.text.Spannable;
import android.text.SpannableString;
import android.text.style.ForegroundColorSpan;
import android.text.style.LeadingMarginSpan;
import android.text.style.StyleSpan;
import android.widget.TextView;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Shared reader typography. List boundaries come from reviewed content data. */
public final class ArticleTypography {
    private static final Pattern MARKER = Pattern.compile("(?m)^(?:\\d{1,3}[.)]|[a-z]\\)|•)[ \\t]+", Pattern.CASE_INSENSITIVE);
    private static final Pattern CHAPTER = Pattern.compile("^\\d{1,2}[A-Z]?[. ]\\s*.*");

    private ArticleTypography() { }

    public static void bind(Context context, TextView view, String type, String role,
                            String label, String value) {
        // Reset every property because body, list and legend rows share a pool.
        view.setTextSize(16);
        view.setTextColor(Ui.INK);
        view.setTypeface(Typeface.create("sans", Typeface.NORMAL));
        view.setLineSpacing(Ui.dp(context, 3), 1.12f);
        view.setPadding(Ui.dp(context, 4), Ui.dp(context, 9), Ui.dp(context, 4), Ui.dp(context, 11));
        view.setBackgroundColor(Color.TRANSPARENT);

        if ("heading".equals(type)) {
            boolean chapter = CHAPTER.matcher(value).matches();
            view.setTextSize(chapter ? 19 : 18);
            view.setTextColor(chapter ? Color.WHITE : Ui.NAVY_DARK);
            view.setTypeface(Typeface.create("sans", Typeface.BOLD));
            view.setPadding(Ui.dp(context, 14), Ui.dp(context, 15), Ui.dp(context, 14), Ui.dp(context, 15));
            view.setBackground(Ui.rounded(chapter ? Ui.NAVY : 0xFFE6EDF3, 8, context));
        } else if ("note".equals(type)) {
            view.setTextSize(15);
            view.setPadding(Ui.dp(context, 14), Ui.dp(context, 13), Ui.dp(context, 14), Ui.dp(context, 13));
            view.setBackground(Ui.outlined(0xFFFFF6D9, 0xFFE2C15C, 8, context));
        } else if ("caption".equals(type)) {
            view.setTextSize(14);
            view.setTextColor(Ui.NAVY);
            view.setPadding(Ui.dp(context, 12), Ui.dp(context, 10), Ui.dp(context, 12), Ui.dp(context, 10));
            view.setBackground(Ui.rounded(0xFFEAF0F5, 6, context));
        } else if ("legend".equals(role)) {
            view.setTextSize(15);
            view.setPadding(Ui.dp(context, 14), Ui.dp(context, 12), Ui.dp(context, 14), Ui.dp(context, 14));
            view.setBackground(Ui.outlined(Color.WHITE, 0xFFD8E1EA, 8, context));
        } else if ("steps".equals(role)) {
            view.setPadding(Ui.dp(context, 12), Ui.dp(context, 11), Ui.dp(context, 12), Ui.dp(context, 12));
            view.setBackground(Ui.rounded(Color.WHITE, 6, context));
        }

        String title = "legend".equals(role) ? (label.isEmpty() ? "Обозначения на рисунке" : label) : "";
        String content = title.isEmpty() ? value : title + "\n\n" + value;
        SpannableString styled = new SpannableString(content);
        if (!title.isEmpty()) {
            styled.setSpan(new StyleSpan(Typeface.BOLD), 0, title.length(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
            styled.setSpan(new ForegroundColorSpan(Ui.NAVY), 0, title.length(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        if (!role.isEmpty()) {
            Matcher markers = MARKER.matcher(content);
            while (markers.find()) {
                int end = content.indexOf('\n', markers.end());
                if (end < 0) end = content.length();
                styled.setSpan(new StyleSpan(Typeface.BOLD), markers.start(), markers.end(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
                styled.setSpan(new ForegroundColorSpan(Ui.BLUE), markers.start(), markers.end(), Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
                styled.setSpan(new LeadingMarginSpan.Standard(0, Ui.dp(context, 30)), markers.start(), end, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
            }
        }
        if ("note".equals(type)) {
            int colon = content.indexOf(':');
            if (colon > 0 && colon < 35) {
                styled.setSpan(new StyleSpan(Typeface.BOLD), 0, colon + 1, Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
            }
        }
        view.setText(styled);
    }
}
