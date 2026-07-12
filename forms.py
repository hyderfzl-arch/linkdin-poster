"""WTForms forms for CSRF protection and validation."""

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
    TimeField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    Regexp,
    URL,
    ValidationError,
)

from validation import is_valid_time_format


class RegisterForm(FlaskForm):
    name = StringField("Full Name", validators=[DataRequired(), Length(max=255)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=8, max=128)]
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired()])


class VerifyForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=255)],
        render_kw={"readonly": True},
    )
    code = StringField(
        "Verification Code",
        validators=[
            DataRequired(),
            Length(min=6, max=8, message="Enter the verification code from your email."),
        ],
        render_kw={"autocomplete": "one-time-code", "inputmode": "numeric"},
    )


class ProfileForm(FlaskForm):
    name = StringField("Display Name", validators=[Optional(), Length(max=255)])
    headline = StringField(
        "LinkedIn Headline",
        validators=[Optional(), Length(max=255)],
    )
    linkedin_url = StringField(
        "LinkedIn Profile URL",
        validators=[
            Optional(),
            URL(),
            Length(max=1000),
            Regexp(
                r"^https://.*",
                message="LinkedIn URLs must use HTTPS.",
            ),
        ],
    )
    linkedin_org_urn = StringField(
        "Company / Organization URN",
        validators=[
            Optional(),
            Length(max=255),
            Regexp(
                r"^urn:li:company:\d+$",
                message="Company URN must be in the form urn:li:company:12345.",
            ),
        ],
        description="Optional urn:li:company:12345 used when publishing to a company page.",
    )
    openai_api_key = PasswordField(
        "OpenAI API Key",
        validators=[Optional(), Length(max=500)],
        description="Leave blank to use the app default key.",
    )
    linkedin_client_id = StringField(
        "LinkedIn Client ID",
        validators=[Optional(), Length(max=500)],
    )
    linkedin_client_secret = PasswordField(
        "LinkedIn Client Secret",
        validators=[Optional(), Length(max=500)],
    )
    timezone = SelectField(
        "Timezone",
        choices=[
            ("UTC", "UTC"),
            ("America/New_York", "America/New_York"),
            ("America/Chicago", "America/Chicago"),
            ("America/Denver", "America/Denver"),
            ("America/Los_Angeles", "America/Los_Angeles"),
            ("Europe/London", "Europe/London"),
            ("Europe/Paris", "Europe/Paris"),
            ("Asia/Dubai", "Asia/Dubai"),
            ("Asia/Karachi", "Asia/Karachi"),
            ("Asia/Mumbai", "Asia/Mumbai"),
            ("Asia/Singapore", "Asia/Singapore"),
            ("Asia/Tokyo", "Asia/Tokyo"),
            ("Australia/Sydney", "Australia/Sydney"),
        ],
    )
    language = SelectField(
        "Language",
        choices=[
            ("en", "English"),
            ("es", "Spanish"),
            ("fr", "French"),
            ("de", "German"),
            ("ur", "Urdu"),
            ("ar", "Arabic"),
        ],
    )
    email_notifications = BooleanField("Enable email notifications")


class SettingsForm(FlaskForm):
    company_name = StringField("Company Name", validators=[Optional(), Length(max=255)])
    company_context = TextAreaField(
        "Company Context", validators=[Optional(), Length(max=2000)]
    )
    default_model = SelectField(
        "Default OpenAI Model",
        choices=[
            ("gpt-4o", "gpt-4o"),
            ("gpt-4o-mini", "gpt-4o-mini"),
            ("gpt-4.1", "gpt-4.1"),
            ("gpt-4.1-mini", "gpt-4.1-mini"),
            ("gpt-4.1-nano", "gpt-4.1-nano"),
            ("o3", "o3"),
            ("o4-mini", "o4-mini"),
        ],
    )
    default_target = SelectField(
        "Default Post Target",
        choices=[
            ("profile", "Personal Profile"),
            ("company", "Company Page"),
            ("choose", "Ask Each Time"),
        ],
    )
    default_inspiration = SelectField(
        "Default Inspiration Source",
        choices=[
            ("manual", "Manual Paste"),
            ("rss", "RSS Feed"),
            ("linkedin_api", "LinkedIn API (approved access)"),
            ("context", "Company Context Only"),
        ],
    )
    post_time = TimeField("Daily Post Time", validators=[DataRequired()])

    def validate_post_time(self, field):
        value = str(field.data)[:5] if field.data else ""
        if not is_valid_time_format(value):
            raise ValidationError("Post time must be in HH:MM 24-hour format.")


class InspirationForm(FlaskForm):
    source = SelectField(
        "Source",
        choices=[
            ("manual", "Manual Paste"),
            ("rss", "RSS Feed"),
            ("linkedin_api", "LinkedIn API (approved access)"),
            ("context", "Company Context Only"),
        ],
        validators=[DataRequired()],
    )
    manual_text = TextAreaField("Post Text", validators=[Optional(), Length(max=4000)])
    rss_url = StringField(
        "RSS Feed URL", validators=[Optional(), URL(), Length(max=1000)]
    )
    linkedin_urn = StringField(
        "LinkedIn Author URN", validators=[Optional(), Length(max=255)]
    )


class GenerateForm(FlaskForm):
    model = SelectField(
        "OpenAI Model",
        choices=[
            ("gpt-4o", "gpt-4o"),
            ("gpt-4o-mini", "gpt-4o-mini"),
            ("gpt-4.1", "gpt-4.1"),
            ("gpt-4.1-mini", "gpt-4.1-mini"),
            ("gpt-4.1-nano", "gpt-4.1-nano"),
            ("o3", "o3"),
            ("o4-mini", "o4-mini"),
        ],
        validators=[DataRequired()],
    )
    target = SelectField(
        "Publish Target",
        choices=[
            ("profile", "Personal Profile"),
            ("company", "Company Page"),
            ("choose", "Ask Each Time"),
        ],
        validators=[DataRequired()],
    )
    inspiration_source = SelectField(
        "Inspiration Source",
        choices=[
            ("manual", "Manual Paste"),
            ("rss", "RSS Feed"),
            ("linkedin_api", "LinkedIn API (approved access)"),
            ("context", "Company Context Only"),
        ],
        validators=[DataRequired()],
    )
    manual_text = TextAreaField(
        "Paste Example Post", validators=[Optional(), Length(max=4000)]
    )
    rss_url = StringField(
        "RSS Feed URL", validators=[Optional(), URL(), Length(max=1000)]
    )
    linkedin_urn = StringField(
        "LinkedIn Author URN", validators=[Optional(), Length(max=255)]
    )
