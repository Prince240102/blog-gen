#!/bin/bash
# WordPress setup script — runs once after containers are up
set -e

echo "⏳ Waiting for WordPress..."
until curl -sf http://localhost:18888/ > /dev/null 2>&1; do sleep 2; done
echo "✅ WordPress is up"

# Install WP-CLI
echo "🔧 Installing WP-CLI..."
docker exec blog-gen-wp bash -c "
curl -sO https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar
chmod +x wp-cli.phar
mv wp-cli.phar /usr/local/bin/wp
" 2>&1 | grep -v "Running as root" || true

# Install WordPress if not already installed
echo "🔧 Installing WordPress..."
docker exec blog-gen-wp wp core install \
  --url='http://localhost:18888' \
  --title='BlogForge Test' \
  --admin_user=admin \
  --admin_password=admin123 \
  --admin_email=admin@test.com \
  --allow-root 2>&1 || echo "Already installed"

# Enable pretty permalinks (required for REST API)
echo "🔗 Enabling pretty permalinks..."
docker exec blog-gen-wp wp rewrite structure '/%postname%/' --allow-root 2>&1

# Ensure both siteurl and home use the external URL (for proper login redirects)
echo "🌐 Setting WordPress URLs..."
docker exec blog-gen-wp wp option update siteurl 'http://localhost:18888' --allow-root 2>&1
docker exec blog-gen-wp wp option update home 'http://localhost:18888' --allow-root 2>&1

# Enable application passwords via functions.php filter
echo "🔑 Enabling application passwords..."
docker exec blog-gen-wp bash -c '
cat >> /var/www/html/wp-content/themes/twentytwentyfive/functions.php << '\''EOF'\''

// Enable application passwords for local HTTP
add_filter( "wp_is_application_passwords_available", "__return_true" );
EOF
' 2>&1

# Create mu-plugin to bypass REST API authentication issues
echo "🔐 Creating REST API auth bypass plugin..."
docker exec blog-gen-wp mkdir -p /var/www/html/wp-content/mu-plugins
docker exec blog-gen-wp bash -c 'cat > /var/www/html/wp-content/mu-plugins/rest-auth.php << '\''EOF'\''
<?php
// REST API authentication bypass for local development
add_filter("rest_authentication_errors", "__return_true");

add_filter("user_has_cap", function($allcaps, $caps, $args, $user) {
    if (!empty($caps)) {
        foreach ($caps as $cap) {
            if (strpos($cap, "post") !== false || strpos($cap, "edit") !== false) {
                $allcaps[$cap] = true;
            }
        }
    }
    if ($user && $user->ID == 1) {
        $allcaps["edit_posts"] = true;
        $allcaps["publish_posts"] = true;
        $allcaps["manage_options"] = true;
    }
    return $allcaps;
}, 999, 4);
EOF
'
docker exec blog-gen-wp chmod 644 /var/www/html/wp-content/mu-plugins/rest-auth.php
docker exec blog-gen-wp chown www-data:www-data /var/www/html/wp-content/mu-plugins/rest-auth.php

# Create application password for admin
EXISTING=$(docker exec blog-gen-wp wp user application-password list admin --fields=name --format=csv --allow-root 2>/dev/null | grep blogforge || echo "")
if [ -n "$EXISTING" ]; then
  echo "🔑 Application password already exists"
  APP_PASS=$(docker exec blog-gen-wp wp user application-password list admin --fields=password --format=csv --allow-root 2>/dev/null | grep blogforge | head -1)
else
  echo "🔑 Creating application password..."
  APP_PASS=$(docker exec blog-gen-wp wp user application-password create admin blogforge --allow-root 2>&1 | grep -oP 'Password: \K.+')
  echo "🔑 App password: $APP_PASS"
fi

if [ -n "$APP_PASS" ]; then
  # Update .env with the generated password
  if [ -f .env ]; then
    sed -i "s|WORDPRESS_APP_PASSWORD=.*|WORDPRESS_APP_PASSWORD=$APP_PASS|" .env
    echo "📝 Updated .env with app password"
  fi
fi

# Restart blog-gen to pick up new env
echo "🔄 Restarting BlogForge..."
docker compose restart blog-gen 2>/dev/null || true

echo ""
echo "✅ Setup complete!"
echo "   WordPress UI:  http://localhost:18888 (admin / admin123)"
echo "   BlogForge:     http://localhost:18001"
echo ""
